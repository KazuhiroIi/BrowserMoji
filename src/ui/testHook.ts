import type { RendererKind } from '../config';
import type { FpsSnapshot, StageTimings } from './fps';

/**
 * e2e テスト用の計測フック（e2e/README.md を参照）。
 * 本番ビルドにも含めるが、実態は window への小さなオブジェクトの登録だけで、
 * 動作への影響は無視できる程度。テスト側は window.__bmTest 経由で
 * fps 統計や描画方式の実態を読む（FPS 表示の DOM をパースするより堅牢）。
 */
export type BmTestApi = {
  /** 直近 5 秒窓の fps 統計（P-3。FpsStats.snapshot() の値） */
  getFpsSnapshot(): FpsSnapshot;
  /**
   * 起動からの累積カウンタ（tick ごとに加算）。5 秒窓は長い停止で立て直されるため、
   * 低 fps 条件では 0 になる。累積値なら任意の区間で fps とステージ別平均を計算できる
   */
  getFrameStats(): { frames: number; stages: StageTimings };
  /** 実効的に使われている描画方式（設定の選択・フォールバックの結果） */
  getRenderer(): RendererKind;
  /** フレームループが動作中か（起動前・例外停止後は false） */
  isRunning(): boolean;
};

declare global {
  interface Window {
    __bmTest?: BmTestApi;
  }
}

export function setTestHook(api: BmTestApi): void {
  window.__bmTest = api;
}
