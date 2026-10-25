import type { FrameSource, GridSpec } from './types';

/**
 * 前処理: 映像をセルグリッドへ縮小する（architecture.md §2）。
 *
 * 映像を「cover」で切り出してから cols×rows に縮小し、
 * 1px = 1 セルの ImageData を作る。drawImage の縮小がセル内の平均に相当するため、
 * ここからセルごとの平均輝度を計算する（ImageData から）。
 */
export function sampleFrame(
  video: HTMLVideoElement,
  grid: GridSpec,
  workCanvas: HTMLCanvasElement,
): FrameSource | null {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw === 0 || vh === 0) return null; // 映像がまだ用意できていない

  const cols = grid.cols;
  const rows = grid.rows;
  if (workCanvas.width !== cols) workCanvas.width = cols;
  if (workCanvas.height !== rows) workCanvas.height = rows;

  const ctx = workCanvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return null;

  // 出力セルは正方形なので、グリッドのアスペクト比は cols / rows。
  // 映像をこのアスペクトに合わせて外接（cover）で切り出す。
  const scale = Math.max(cols / vw, rows / vh);
  const sw = cols / scale;
  const sh = rows / scale;
  const sx = (vw - sw) / 2;
  const sy = (vh - sh) / 2;
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, cols, rows);

  const image = ctx.getImageData(0, 0, cols, rows);
  return { width: cols, height: rows, data: image.data };
}
