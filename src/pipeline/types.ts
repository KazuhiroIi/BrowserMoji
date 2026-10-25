import type { AppConfig } from '../config';

/**
 * 変換パイプラインの段階ごとの境界（architecture.md §2）。
 * 各段階の実装は差し替え可能にする（N-3）。
 */

/** 1 セルぶんの特徴量 */
export type CellFeature = {
  /** 平均輝度 0..1 */
  luminance: number;
  /** 勾配の強さ（0..1 を想定。Sobel を正規化した値） */
  gradMagnitude: number;
  /** 勾配の向き（ラジアン。画面座標系・y は下向き） */
  gradAngle: number;
  // 将来拡張: color, segmentClass, 領域内の濃淡パターン など
};

/** 前処理でセルグリッドに縮小済みの 1 フレーム（1px = 1 セル） */
export type FrameSource = {
  /** セル数（列） */
  width: number;
  /** セル数（行） */
  height: number;
  /** RGBA の画素配列 */
  data: Uint8ClampedArray;
};

/** セルグリッドの配置。cellWidth / cellHeight は出力 canvas 上の 1 セルのサイズ（px） */
export type GridSpec = {
  cols: number;
  rows: number;
  cellWidth: number;
  cellHeight: number;
};

export interface FeatureExtractor {
  extract(frame: FrameSource, grid: GridSpec, cfg: AppConfig): CellFeature[];
}

/** 各セルの文字 ID（グリフアトラス上のインデックス）を返す */
export interface GlyphSelector {
  select(features: CellFeature[], cfg: AppConfig): Uint16Array;
}

/** color は F-10（カラー表示）採用時に使う */
export interface Renderer {
  render(glyphIds: Uint16Array, grid: GridSpec, cfg: AppConfig, color?: Uint8Array): void;
}
