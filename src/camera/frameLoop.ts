/**
 * フレーム取得（architecture.md §6）。
 * requestVideoFrameCallback が使えればそれを、無ければ requestAnimationFrame で代替する。
 * どちらも 1 回しか発火しないため、コールバック内で次のフレームを予約し直してループを維持する。
 * 戻り値は取得を止める関数。
 */
export function startFrameLoop(
  video: HTMLVideoElement,
  tick: (timeMs: number) => void,
): () => void {
  let stopped = false;
  let handle = 0;
  const useVideoFrameCallback = 'requestVideoFrameCallback' in HTMLVideoElement.prototype;

  const loop = (now: number): void => {
    if (stopped) return;
    tick(now);
    schedule();
  };

  const schedule = (): void => {
    if (stopped) return;
    if (useVideoFrameCallback) {
      handle = video.requestVideoFrameCallback(loop);
    } else {
      handle = requestAnimationFrame(loop);
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
