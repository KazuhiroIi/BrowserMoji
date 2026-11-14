import { expect, test, type Page } from '@playwright/test';
import { PNG } from 'pngjs';
import { setupCameraMock, startApp, waitForFrames } from './helpers';

/**
 * テクスチャ幅上限への対応の確認（D-011）。
 *
 * 実機（OPPO A5 2020）で、文字セットを 62 文字に増やした際にアトラス canvas が
 * 5952px 幅になり MAX_TEXTURE_SIZE を超え、texImage2D がサイレントに失敗した結果、
 * 不完全テクスチャ（サンプル値 = 不透明黒）を参照して全画面が真っ黒になる不具合が
 * あった。ヘッドレスの GPU は上限が大きいため再現しないので、getContext を
 * ラップして MAX_TEXTURE_SIZE を小さく偽装し、実機と同じ条件を作って確認する。
 *
 * - 上限内に収まるようアトラスのセル幅が縮む場合は WebGL2 のまま描画を続けること
 * - 上限が極端に小さく収められない場合は Canvas 2D にフォールバックして描画を続けること
 *   （どちらの経路でも「真っ黒な画面」にはならないこと）
 */

/** MAX_TEXTURE_SIZE の取得結果を強制する（getContext の戻り値を Proxy で包む） */
function forceMaxTextureSize(size: number): void {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (...args: unknown[]): unknown {
    const ctx = original.apply(this, args as Parameters<typeof HTMLCanvasElement.prototype.getContext>);
    if (args[0] === 'webgl2' && ctx) {
      const target = ctx as WebGL2RenderingContext;
      return new Proxy(target, {
        get(t, prop) {
          if (prop === 'getParameter') {
            return (p: number) => (p === t.MAX_TEXTURE_SIZE ? size : t.getParameter(p));
          }
          const value = t[prop as keyof WebGL2RenderingContext];
          return typeof value === 'function' ? (value as (...a: unknown[]) => unknown).bind(t) : value;
        },
      });
    }
    return ctx;
  };
}

/** 輝度（0..255）の標準偏差と平均。一色（真っ黒/白）なら stddev が 0 に近くなる */
function luminanceStats(png: PNG): { mean: number; stddev: number } {
  const n = png.width * png.height;
  let sum = 0;
  let sum2 = 0;
  for (let i = 0; i < n; i++) {
    const y = 0.299 * png.data[i * 4] + 0.587 * png.data[i * 4 + 1] + 0.114 * png.data[i * 4 + 2];
    sum += y;
    sum2 += y * y;
  }
  const mean = sum / n;
  return { mean, stddev: Math.sqrt(sum2 / n - mean * mean) };
}

async function expectRenderer(page: Page, expected: string): Promise<void> {
  await page.waitForFunction(
    (value) => window.__bmTest?.getRenderer() === value,
    expected,
    { timeout: 30_000 },
  );
}

test('MAX_TEXTURE_SIZE=4096 でも WebGL2 のまま描画する（アトラスのセル幅を縮める）', async ({ context }) => {
  await context.addInitScript(forceMaxTextureSize, 4096);
  const page = await setupCameraMock(context, 'still');
  await startApp(page);
  // フォールバックしていないこと（フォールバックすると canvas2d になる）
  await expectRenderer(page, 'webgl2');
  await waitForFrames(page, 3);
  const shot = await page.locator('canvas.ascii-canvas').screenshot();
  const png = PNG.sync.read(shot);
  const { mean, stddev } = luminanceStats(png);
  console.log(`[stat] maxTex=4096: 平均輝度 = ${mean.toFixed(1)} / 標準偏差 = ${stddev.toFixed(1)}`);
  expect(stddev, '出力が一色でないこと').toBeGreaterThan(10);
  expect(mean, '真っ黒でないこと（不完全テクスチャは不透明黒を返す）').toBeGreaterThan(30);
});

test('MAX_TEXTURE_SIZE が極端に小さい場合は Canvas 2D にフォールバックする', async ({ context }) => {
  // 62 グリフ × 最小セル 16px = 992px でも収まらない上限 → アトラス構築が例外になり
  // WebGL2 は broken 扱いで Canvas 2D へフォールバックする
  await context.addInitScript(forceMaxTextureSize, 512);
  const page = await setupCameraMock(context, 'still');
  await startApp(page);
  await expectRenderer(page, 'canvas2d');
  await waitForFrames(page, 3);
  const shot = await page.locator('canvas.ascii-canvas').screenshot();
  const png = PNG.sync.read(shot);
  const { mean, stddev } = luminanceStats(png);
  console.log(`[stat] maxTex=512 フォールバック: 平均輝度 = ${mean.toFixed(1)} / 標準偏差 = ${stddev.toFixed(1)}`);
  expect(stddev, 'フォールバック後も出力が一色でないこと').toBeGreaterThan(10);
  expect(mean, 'フォールバック後も真っ黒でないこと').toBeGreaterThan(30);
});
