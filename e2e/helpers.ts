import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { BrowserContext, Page } from '@playwright/test';

/** リポジトリのルート（playwright.config.ts と同じ場所） */
export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** テスト用メディア（data/ は .gitignore 済み。npm run test:media で生成する） */
export const CLIP_PATH = path.join(ROOT, 'data', 'sample30.webm');
export const STILL_PATH = path.join(ROOT, 'data', 'still30.webm');

/** vite preview は base: /BrowserMoji/ で配信する（D-007） */
export const APP_URL = '/BrowserMoji/';

/** 実機（スマートフォン縦持ち）に近い固定ビューポート。計測・比較の再現性のため固定する */
export const VIEWPORT = { width: 390, height: 844 };
export const DEVICE_SCALE_FACTOR = 2;

/**
 * e2e テストから読むアプリ側の計測フック（src/ui/testHook.ts）。
 * 本ファイル内では src の型を import しないため、必要な形だけをここで宣言する。
 */
type BmTestApi = {
  getFpsSnapshot(): {
    avgFps: number;
    minFps: number;
    camFps: number | null;
    stages: { pre: number; read: number; feat: number; sel: number; draw: number };
  };
  getFrameStats(): {
    frames: number;
    stages: { pre: number; read: number; feat: number; sel: number; draw: number };
  };
  getRenderer(): string;
  isRunning(): boolean;
};

declare global {
  interface Window {
    __bmTest?: BmTestApi;
  }
}

/**
 * getUserMedia をスタブし、指定された動画を再生する video 要素をカメラの代わりに渡す
 * （アプリ側のコード変更は不要。アプリは通常どおり開始ボタンから起動するので、
 * 実機と同じフローを通る）。
 *
 * video 要素をカメラ代わりにする理由は 2 つ:
 * - 実機と同じくカメラ実効 fps（30fps）が上限になる条件で計測できる
 * - ヘッドレス Chromium では canvas.captureStream() 由来の MediaStream では
 *   requestVideoFrameCallback（フレームループの駆動源）が発火しないため、
 *   video.captureStream() 経由に統一する（実測による。probe-stream の結果）
 */
export function cameraVideoMock(src: string): void {
  navigator.mediaDevices.getUserMedia = async () => {
    const video = document.createElement('video');
    video.src = src;
    video.loop = true;
    video.muted = true;
    video.autoplay = true;
    // video 要素は画面に出さない（app.ts の hidden-video と同じ扱い）
    video.style.position = 'fixed';
    video.style.width = '1px';
    video.style.height = '1px';
    video.style.opacity = '0';
    video.style.pointerEvents = 'none';
    document.body.append(video);
    await video.play();
    return video.captureStream();
  };
}

/**
 * テスト用メディアを e2e-assets/ の URL で配信する（vite の配信物に含めないため、
 * Playwright の route で data/ 配下のファイルを返す）。
 * その後 init script で getUserMedia をスタブし、テスト用ページを返す。
 *
 * mode:
 * - 'stream': 撮影映像（30fps に変換）を流す。性能計測・統計チェック用
 * - 'still' : 静止画 1 枚から作った全フレーム同一の動画を流す。
 *             入力が常に同一になるため出力の pixel 比較（正しさの確認）ができる
 */
export async function setupCameraMock(
  context: BrowserContext,
  mode: 'stream' | 'still',
): Promise<Page> {
  const src = mode === 'stream' ? '/e2e-assets/sample30.webm' : '/e2e-assets/still30.webm';
  await context.route('**/e2e-assets/sample30.webm', (route) =>
    route.fulfill({ path: CLIP_PATH, contentType: 'video/webm' }),
  );
  await context.route('**/e2e-assets/still30.webm', (route) =>
    route.fulfill({ path: STILL_PATH, contentType: 'video/webm' }),
  );
  await context.addInitScript(cameraVideoMock, src);
  return context.newPage();
}

/** 開始ボタンを押してアプリを起動し、フレームループが動き出すまで待つ（実機と同じフロー） */
export async function startApp(page: Page): Promise<void> {
  await page.goto(APP_URL);
  await page.locator('.start-button').click();
  await page.waitForSelector('canvas.ascii-canvas');
  await page.waitForFunction(() => window.__bmTest?.isRunning() === true);
}

/** 累積フレームカウンタが n を超えるまで待つ（長い 1 フレームにも耐えるよう timeout を指定できる） */
export async function waitForFrames(page: Page, n: number, timeout = 120_000): Promise<void> {
  await page.waitForFunction(
    (target) => (window.__bmTest?.getFrameStats().frames ?? 0) >= target,
    n,
    { timeout },
  );
}

/** 累積カウンタを読む（区間計測の両端で使う） */
export async function readFrameStats(page: Page): Promise<{
  frames: number;
  stages: { pre: number; read: number; feat: number; sel: number; draw: number };
}> {
  return page.evaluate(() => window.__bmTest!.getFrameStats());
}
