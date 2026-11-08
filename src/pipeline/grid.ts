import type { GridSpec } from './types';

/**
 * 出力 canvas のサイズと列数からセルグリッドを計算する。
 * 1 セル = 全角 1 文字の正方形に近いセル（T-2）。行数は画面比から自動計算する。
 * featurePx は特徴量計算のセル内分解能（cfg.featurePx）。
 */
export function computeGrid(
  canvasWidth: number,
  canvasHeight: number,
  columns: number,
  featurePx: number,
): GridSpec {
  const cols = Math.max(1, Math.floor(columns));
  const cellWidth = canvasWidth / cols;
  const cellHeight = cellWidth; // 正方形のセル（T-2）
  const rows = Math.max(1, Math.floor(canvasHeight / cellHeight));
  return { cols, rows, cellWidth, cellHeight, featurePx: Math.max(1, Math.round(featurePx)) };
}
