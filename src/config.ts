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
export const defaultConfig: AppConfig = {
  renderer: 'webgl2',
  columns: 48,
  contrast: 1.0,
  edgeThreshold: 0.2,
  edgePriority: 0.5,
  invert: false,
  charset: 'default',
  // EXP-1 で実機 fps を計測するため既定 ON。設定パネルで OFF にできる
  showFps: true,
};
