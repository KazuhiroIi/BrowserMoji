import type { FrameSource, GridSpec } from './types';

/** sampleFrame の戻り値。timings は blit（pre）と読み出し（read）の処理時間（ms、P-3 の計測用） */
export type SampledFrame = {
  frame: FrameSource | null;
  timings: {
    /** 前処理 blit: video → work canvas の drawImage（ms） */
    pre: number;
    /** 前処理読み出し: work canvas からの getImageData（ms） */
    read: number;
  };
};

/**
 * 前処理: 映像をセルグリッドへ縮小する（architecture.md §2）。
 *
 * 映像を「cover」で切り出してから cols×rows に縮小し、
 * 1px = 1 セルの ImageData を作る。drawImage の縮小がセル内の平均に相当するため、
 * ここからセルごとの平均輝度を計算する（ImageData から）。
 *
 * blit（drawImage）と読み出し（getImageData）はコストが異なるため、
 * 処理時間を timings で個別に返す（P-3 のデバッグ表示用）。
 */
export function sampleFrame(
  video: HTMLVideoElement,
  grid: GridSpec,
  workCanvas: HTMLCanvasElement,
): SampledFrame {
  const timings = { pre: 0, read: 0 };
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw === 0 || vh === 0) return { frame: null, timings }; // 映像がまだ用意できていない

  const cols = grid.cols;
  const rows = grid.rows;
  if (workCanvas.width !== cols) workCanvas.width = cols;
  if (workCanvas.height !== rows) workCanvas.height = rows;

  const ctx = workCanvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return { frame: null, timings };

  // 出力セルは正方形なので、グリッドのアスペクト比は cols / rows。
  // 映像をこのアスペクトに合わせて外接（cover）で切り出す。
  const scale = Math.max(cols / vw, rows / vh);
  const sw = cols / scale;
  const sh = rows / scale;
  const sx = (vw - sw) / 2;
  const sy = (vh - sh) / 2;

  const blitStart = performance.now();
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, cols, rows);
  timings.pre = performance.now() - blitStart;

  const readStart = performance.now();
  const image = ctx.getImageData(0, 0, cols, rows);
  timings.read = performance.now() - readStart;

  return { frame: { width: cols, height: rows, data: image.data }, timings };
}
