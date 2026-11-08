import type { AppConfig } from '../config';

/**
 * 変換パイプラインの段階ごとの境界（architecture.md §2）。
 * 各段階の実装は差し替え可能にする（N-3）。
 */

/** 1 セルぶんの特徴量 */
export type CellFeature = {
  /** 平均輝度 0..1（セル内の画素平均 = 基準実装の block_mean） */
  luminance: number;
  /**
   * 勾配の強さ（0..1 を想定。Sobel を正規化した値）。
   * EXP-2 発見 1: エッジ検出にはセル内**最大** |勾配| を使う
   * （セル平均だと細いエッジが 1/featurePx に希釈される。D-009）
   */
  gradMagnitude: number;
  /** 勾配の向き（ラジアン。画面座標系・y は下向き。セル内平均勾配ベクトルの向き） */
  gradAngle: number;
  /**
   * 勾配の整合性（0..1。|平均勾配ベクトル| / 平均 |勾配|、基準実装の coherence）。
   * EXP-2 発見: 境界を実際に含むセルだけが高い。隣のセルは最大勾配だけ高く
   * 向きが打ち消し合うため、この値でエッジ置換の対象を絞る（D-009）
   */
  gradCoherence: number;
  // 将来拡張: color, segmentClass, 領域内の濃淡パターン など
};

/**
 * 前処理で縮小済みの 1 フレーム。
 * 1 セル = featurePx × featurePx ピクセル（grid.featurePx 参照。EXP-2 発見 1 の
 * セル内最大勾配を取るためにセル内部の画素を保持する）
 */
export type FrameSource = {
  /** 幅（px。= cols × featurePx） */
  width: number;
  /** 高さ（px。= rows × featurePx） */
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
  /** 特徴量計算のセル内分解能（1 セルの 1 辺 px。cfg.featurePx の値） */
  featurePx: number;
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
