/**
 * AppConfig — 調整可能な値を 1 か所に集約する（architecture.md 設計原則 2、D-003）。
 * UI・描画ループ・将来の保存・実験が同じ設定を読む。
 */
/** 描画方式（architecture.md §5、D-008） */
export type RendererKind = 'canvas2d' | 'webgl2';

export type AppConfig = {
  /** 描画方式（Canvas 2D と WebGL2。切替 UI で変更し、次フレームから反映する） */
  renderer: RendererKind;
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
  /** 使用する文字セット（F-13 で切り替え UI を追加する予定） */
  charset: string;
  /** デバッグ用 fps 表示（P-3） */
  showFps: boolean;
};

// 既定値は原則暫定値。実験（EXP-1 〜 EXP-4、architecture.md §10）で決める。
// renderer の既定は EXP-1 の結果により 'webgl2' に確定（D-008）。WebGL2 の生成失敗・
// context lost 時は canvas2d にフォールバックする（app.ts の ensureRenderer）。
// columns・edgeThreshold・charset の既定は EXP-2 / EXP-3 の結果により更新（D-009 / D-010）。
export const defaultConfig: AppConfig = {
  renderer: 'webgl2',
  // EXP-2 のユーザー評価「80 列でもう少し細かくてもいい」を受け、100 にする。
  // P-1 / P-2 との兼ね合いは EXP-1 の実機 fps（WebGL2 で余裕あり）と fps オーバーレイで確認する
  columns: 100,
  contrast: 1.0,
  // EXP-2 で調整した基準実装の値（selector.py / config.py の EDGE_THRESHOLD、D-009）
  edgeThreshold: 0.14,
  edgePriority: 0.5,
  // EXP-2 の基準実装の COHERENCE_MIN（selector.py、D-009）
  coherenceMin: 0.25,
  // EXP-2 / EXP-3 の基準実装の featurePx（config.py の DEFAULT_FS）
  featurePx: 16,
  invert: false,
  // EXP-3 で確定した採用セット（density 27 + line 35、D-010 / T-4）
  charset: 'all',
  // EXP-1 で実機 fps を計測するため既定 ON。設定パネルで OFF にできる
  showFps: true,
};
