/**
 * フレーム取得（architecture.md §6）。
 * requestVideoFrameCallback が使えればそれを、無ければ requestAnimationFrame で代替する。
 * 戻り値は取得を止める関数。
 */
export function startFrameLoop(
  video: HTMLVideoElement,
  tick: (timeMs: number) => void,
): () => void {
  let stopped = false;
  let handle = 0;
  const useVideoFrameCallback = 'requestVideoFrameCallback' in HTMLVideoElement.prototype;

  const schedule = (): void => {
    if (stopped) return;
    if (useVideoFrameCallback) {
      handle = video.requestVideoFrameCallback((now) => tick(now));
    } else {
      handle = requestAnimationFrame((now) => tick(now));
    }
  };

  schedule();
  return () => {
    stopped = true;
    if (useVideoFrameCallback) {
      video.cancelVideoFrameCallback(handle);
    } else {
      cancelAnimationFrame(handle);
    }
  };
}
