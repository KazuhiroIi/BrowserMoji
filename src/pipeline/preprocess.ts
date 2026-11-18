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
 * 映像を「cover」で切り出してから cols×featurePx × rows×featurePx に縮小する
 * （1 セル = featurePx × featurePx 画素）。EXP-2 発見 1・2（D-009）により、
 * エッジ検出はセル内**最大** |Sobel| で行うため、セル内部の画素を保持する
 * （1px = 1 セルに縮小すると細いエッジが希釈され検出できない）。
 * blit（drawImage）と読み出し（getImageData）はコストが異なるため、
 * 処理時間を timings で個別に返す（P-3 のデバッグ表示用）。
 */
export function sampleFrame(
  video: HTMLVideoElement,
  grid: GridSpec,
  workCanvas: HTMLCanvasElement,
  mirror = false,
): SampledFrame {
  const timings = { pre: 0, read: 0 };
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw === 0 || vh === 0) return { frame: null, timings }; // 映像がまだ用意できていない

  const fs = grid.featurePx;
  const width = grid.cols * fs;
  const height = grid.rows * fs;
  if (workCanvas.width !== width) workCanvas.width = width;
  if (workCanvas.height !== height) workCanvas.height = height;

  const ctx = workCanvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return { frame: null, timings };

  // 出力セルは正方形なので、グリッドのアスペクト比は width / height。
  // 映像をこのアスペクトに合わせて外接（cover）で切り出す。
  const scale = Math.max(width / vw, height / vh);
  const sw = width / scale;
  const sh = height / scale;
  const sx = (vw - sw) / 2;
  const sy = (vh - sh) / 2;

  const blitStart = performance.now();
  if (mirror) {
    ctx.save();
    ctx.translate(width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, width, height);
    ctx.restore();
  } else {
    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, width, height);
  }
  timings.pre = performance.now() - blitStart;

  const readStart = performance.now();
  const image = ctx.getImageData(0, 0, width, height);
  timings.read = performance.now() - readStart;

  return { frame: { width, height, data: image.data }, timings };
}
