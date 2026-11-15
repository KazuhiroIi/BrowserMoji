import fs from 'node:fs';
import path from 'node:path';
import { test, type BrowserContext, type Page } from '@playwright/test';
import {
  CLIP_PATH,
  DEVICE_SCALE_FACTOR,
  ROOT,
  VIEWPORT,
  readFrameStats,
  setupCameraMock,
  startApp,
  switchPipelineModeViaUi,
  waitForFrames,
} from './helpers';

/**
 * 一時計測用: classic と selectorA の処理速度を同じ条件で比較する。
 * - 入力は data/sample30.webm（data/sample.mp4 から tools/e2e/prepare_media.py で生成。
 *   sample.mp4 は H.264 で Playwright Chromium が再生できないため派生クリップを使う）
 * - CPU スロットリング 1x / 4x / 20x の各条件で、mode ごとに context を作り直して計測
 * - fps は累積フレームカウンタの差分、ステージ別は累積ステージ時間の差分から算出
 * - 結果は results/perf-selector-compare.json に保存する（合否判定なし）
 */

const RATES = [1, 4, 20];
const MEASURE_MS = 15_000;
const WARMUP_FRAMES = 3;
const MODES = ['classic', 'selectorA'] as const;

const RESULTS_DIR = path.join(ROOT, 'results');
const OUT_PATH = path.join(RESULTS_DIR, 'perf-selector-compare.json');

type StageMs = { pre: number; read: number; feat: number; sel: number; draw: number };

type Entry = {
  mode: string;
  rate: number;
  fps: number;
  frames: number;
  stages: StageMs;
  renderer: string;
};

test.beforeAll(() => {
  if (!fs.existsSync(CLIP_PATH)) {
    throw new Error(`${CLIP_PATH} がありません。npm run test:media を実行してください`);
  }
});

test('classic vs selectorA 性能比較', async ({ browser }) => {
  test.setTimeout(1_200_000);

  const entries: Entry[] = [];
  for (const rate of RATES) {
    for (const mode of MODES) {
      const context: BrowserContext = await browser.newContext({
        viewport: VIEWPORT,
        deviceScaleFactor: DEVICE_SCALE_FACTOR,
      });
      const page = await setupCameraMock(context, 'stream');
      const cdp = await context.newCDPSession(page);
      await cdp.send('Emulation.setCPUThrottlingRate', { rate });

      await startApp(page);
      await pinMode(page, mode);
      // モード切替でアトラス再生成が走るため、切替後にもう一度ウォームアップ
      await waitForFrames(page, WARMUP_FRAMES, 300_000);
      const before = await readFrameStats(page);
      const t0 = Date.now();
      await page.waitForTimeout(MEASURE_MS);
      const after = await readFrameStats(page);
      const elapsed = (Date.now() - t0) / 1000;

      const renderer = await page.evaluate(() => window.__bmTest!.getRenderer());
      const frames = after.frames - before.frames;
      const stages = divideStages(subStages(after.stages, before.stages), frames);
      entries.push({ mode, rate, fps: frames / elapsed, frames, stages, renderer });
      const s = stages;
      console.log(
        `[compare] CPU ${rate}x ${mode}: fps=${(frames / elapsed).toFixed(2)} ` +
          `(${frames} frames / ${elapsed.toFixed(1)} s) | pre=${s.pre.toFixed(1)} read=${s.read.toFixed(1)} ` +
          `feat=${s.feat.toFixed(1)} sel=${s.sel.toFixed(1)} draw=${s.draw.toFixed(1)} ms`,
      );
      await context.close();
    }
  }

  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.writeFileSync(
    OUT_PATH,
    JSON.stringify({ timestamp: new Date().toISOString(), entries }, null, 2),
  );
  console.log(`\n保存: ${OUT_PATH}`);

  console.log('\n=== classic vs selectorA（fps・ステージ別平均 ms） ===');
  console.log('rate    mode       fps     | pre    read   feat   sel    draw');
  for (const rate of RATES) {
    const byMode = new Map(entries.filter((e) => e.rate === rate).map((e) => [e.mode, e]));
    const c = byMode.get('classic');
    const a = byMode.get('selectorA');
    if (c && a) {
      console.log(`${String(rate).padEnd(7)} classic    ${c.fps.toFixed(2).padEnd(7)} | ${fmtStages(c.stages)}`);
      console.log(`${' '.repeat(7)} selectorA  ${a.fps.toFixed(2).padEnd(7)} | ${fmtStages(a.stages)}`);
      if (a.fps > 0 && c.fps > 0) {
        console.log(
          `${' '.repeat(7)} 差: selectorA は classic の ${(c.fps / a.fps).toFixed(2)} 倍の fps（selectorA は ${(((c.fps - a.fps) / c.fps) * 100).toFixed(0)}% 遅い）`,
        );
      }
    }
  }
});

async function pinMode(page: Page, mode: 'classic' | 'selectorA'): Promise<void> {
  if (mode === 'selectorA') {
    await switchPipelineModeViaUi(page, 'selectorA');
  }
  // classic は既定モードなのでそのまま
}

function subStages(a: StageMs, b: StageMs): StageMs {
  return {
    pre: a.pre - b.pre,
    read: a.read - b.read,
    feat: a.feat - b.feat,
    sel: a.sel - b.sel,
    draw: a.draw - b.draw,
  };
}

function divideStages(s: StageMs, frames: number): StageMs {
  if (frames <= 0) return { pre: 0, read: 0, feat: 0, sel: 0, draw: 0 };
  return { pre: s.pre / frames, read: s.read / frames, feat: s.feat / frames, sel: s.sel / frames, draw: s.draw / frames };
}

function fmtStages(s: StageMs): string {
  return [s.pre, s.read, s.feat, s.sel, s.draw].map((v) => v.toFixed(1).padEnd(6)).join(' ');
}
