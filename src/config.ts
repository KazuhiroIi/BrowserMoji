/**
 * AppConfig — 調整可能な値を 1 か所に集約する（architecture.md 設計原則 2、D-003）。
 * UI・描画ループ・将来の保存・実験が同じ設定を読む。
 */
/** 描画方式（architecture.md §5、D-008） */
export type RendererKind = 'canvas2d' | 'webgl2';

/**
 * パイプラインの方式（文字セット・文字選択・前処理解像度のまとまり）。
 * - classic: EXP-2 / EXP-3 適用前の挙動（076886d より前。旧文字セット +
 *   等分量子化の濃度選択 + 4 方向の線置換 + featurePx = 1。D-009 / D-010 の前）
 * - selectorA: 基準実装（tools/prototype/selector.py の SelectorA）と同じ意味の
 *   現行方式（計測濃度の最近傍、セル内最大 |Sobel|、整合性チェック、
 *   向き + 太さのスコア式。D-009）+ EXP-3 採用文字セット（D-010）
 */
export type PipelineMode = 'classic' | 'selectorA';

export type AppConfig = {
  /** 描画方式（Canvas 2D と WebGL2。切替 UI で変更し、次フレームから反映する） */
  renderer: RendererKind;
  /** パイプラインの方式（切替 UI で変更し、次フレームから反映する） */
  mode: PipelineMode;
  /** 列数。行数は画面のアスペクト比から自動計算する */
  columns: number;
  /** 輝度の階調の強さ（1 = 無調整） */
  contrast: number;
  /** エッジとして扱う勾配のしきい値（0..1） */
  edgeThreshold: number;
  /** エッジ文字への置き換えのしやすさ（0..1。大きいほど置きやすい） */
  edgePriority: number;
  /**
   * エッジ置換の整合性の下限（0..1。EXP-2 の基準実装の COHERENCE_MIN）。
   * セル内の勾配ベクトルの向きが一致している割合。細い線の隣など向きが
   * 打ち消し合うセル（境界を含まないセル）ではエッジ置換しない（D-009）
   */
  coherenceMin: number;
  /**
   * 特徴量計算のセル内分解能（1 セルの 1 辺 = この px 数で Sobel を計算する）。
   * EXP-2 発見 1・2: 細いエッジはセル平均で希釈されるため、セル内最大 |Sobel|
   * で検出する。そのためにはセル内部の画素が必要（基準実装の featurePx = 16）。
   * CPU 負荷が高い場合の調整値（8 などに下げる）。UI へは出さない（P-3 の fps で判断）
   */
  featurePx: number;
  /** 白黒反転（既定: 白背景＋黒文字、T-6） */
  invert: boolean;
  /** 左右反転（ミラー表示。前面カメラ時は既定で true） */
  mirror: boolean;
  /** エッジマスのみ描画（フィラーの濃度文字を描画せず空白にする） */
  edgeOnly: boolean;
  /** 使用する文字セット（F-13 で切り替え UI を追加する予定） */
  charset: string;
  /**
   * カスタムフィラー文字セット（null のときはモード既定の文字セットを使う）。
   * 設定パネルの入力欄からリアルタイムに編集できる。
   */
  fillerChars: string | null;
  /** デバッグ用 fps 表示（P-3） */
  showFps: boolean;
};

// 既定値は原則暫定値。実験（EXP-1 〜 EXP-4、architecture.md §10）で決める。
// renderer の既定は EXP-1 の結果により 'webgl2' に確定（D-008）。WebGL2 の生成失敗・
// context lost 時は canvas2d にフォールバックする（app.ts の ensureRenderer）。
// 既定の mode は classic（076886d 適用前の挙動）。columns・edgeThreshold・charset は
// モードごとの既定値（modeDefaults）を持ち、モード切替時に入れ替わる。
export const defaultConfig: AppConfig = {
  renderer: 'webgl2',
  mode: 'classic',
  // classic モードの既定値（076886d 適用前の値）
  columns: 48,
  contrast: 1.0,
  edgeThreshold: 0.2,
  edgePriority: 0.5,
  // EXP-2 の基準実装の COHERENCE_MIN（selector.py、D-009）。selectorA モードでのみ使う
  coherenceMin: 0.25,
  // EXP-2 / EXP-3 の基準実装の featurePx（config.py の DEFAULT_FS）。
  // selectorA モードでのみ使う（classic モードは 1px = 1 セル。effectiveFeaturePx）
  featurePx: 16,
  invert: false,
  mirror: false,
  edgeOnly: false,
  // classic モードの既定文字セット（076886d 適用前のダミーセット）
  charset: 'default',
  fillerChars: null,
  // EXP-1 で実機 fps を計測するため既定 ON。設定パネルで OFF にできる
  showFps: true,
};

/** モードごとの既定値（モード切替時に入れ替える。ユーザーが後から再調整できる） */
export const modeDefaults: Record<PipelineMode, Pick<AppConfig, 'columns' | 'edgeThreshold' | 'charset'>> = {
  // 076886d 適用前の値
  classic: { columns: 48, edgeThreshold: 0.2, charset: 'default' },
  // EXP-2 / EXP-3 の適用値（D-009 / D-010）
  selectorA: { columns: 100, edgeThreshold: 0.14, charset: 'all' },
};

/** モード切替時にモードの既定値へ入れ替える（columns・edgeThreshold・charset・fillerChars） */
export function applyModeDefaults(cfg: AppConfig): void {
  Object.assign(cfg, modeDefaults[cfg.mode], { fillerChars: null });
}

/**
 * 特徴量計算で使うセル内分解能（px）。classic モードは 1px = 1 セル
 * （076886d 適用前の前処理と同じ。セル内平均 = 縮小後の 1 画素）。selectorA モードは
 * セル内最大 |Sobel| を取るため cfg.featurePx（EXP-2 発見 1・2、D-009）。
 */
export function effectiveFeaturePx(cfg: AppConfig): number {
  return cfg.mode === 'classic' ? 1 : cfg.featurePx;
}
