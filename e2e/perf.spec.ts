import fs from 'node:fs';
import path from 'node:path';
import { expect, test, type BrowserContext } from '@playwright/test';
import {
  CLIP_PATH,
  DEVICE_SCALE_FACTOR,
  ROOT,
  VIEWPORT,
  readFrameStats,
  setupCameraMock,
  startApp,
  waitForFrames,
} from './helpers';

/**
 * 性能計測（相対値のリグレッション検知）:
 * - Chromium の CDP Emulation.setCPUThrottlingRate で CPU を 1x / 4x / 20x に遅くし、
 *   「CPU が律速する状況」で fps とステージ別処理時間を計測する
 * - GPU は実機のものではないため、絶対値（実機で何 fps 出るか）は取れない。
 *   同一環境・同一入力での相対比較（変更前後で何倍遅くなったか）に使う
 * - fps は累積フレームカウンタ（window.__bmTest.getFrameStats()）の差分から出す。
 *   FpsStats の 5 秒窓は 1 秒以上のフレーム間隔で窓を立て直すため、低 fps 条件では
 *   窓ベースの値が 0 になる。窓ベースの値（avgFps / minFps / camFps）は参考値として記録する
 * - 結果は results/perf-latest.json に保存し、前回実行との差分を表示する。
 *   合否判定はしない（数値の揺らぎを掴んでから閾値を決める）
 */

const RATES = [1, 4, 20];
/** 1 条件あたりの計測時間。長いほど揺らぎが減るが、20x では 1 フレームが十数秒になる */
const MEASURE_MS = 15_000;
/** ウォームアップ: 初回のアトラス生成や JIT を除外するために処理させてから計測するフレーム数 */
const WARMUP_FRAMES = 3;

const RESULTS_DIR = path.join(ROOT, 'results');
const LATEST_PATH = path.join(RESULTS_DIR, 'perf-latest.json');
const HISTORY_DIR = path.join(RESULTS_DIR, 'perf-history');

type StageMs = { pre: number; read: number; feat: number; sel: number; draw: number };

type PerfEntry = {
  rate: number;
  /** 累積カウンタから出した実測 fps（計測区間の処理フレーム数 / 経過秒） */
  fps: number;
  /** 計測区間に処理したフレーム数（0 なら事実上停止している） */
  frames: number;
  /** FpsStats の 5 秒窓による参考値 */
  avgFps: number;
  minFps: number;
  camFps: number | null;
  stages: StageMs;
  renderer: string;
};

test.beforeAll(() => {
  if (!fs.existsSync(CLIP_PATH)) {
    throw new Error(
      `${CLIP_PATH} がありません。ffmpeg で生成する必要があるため、npm run test:media を実行してください`,
    );
  }
});

test('性能計測: CPU スロットリング 1x / 4x / 20x で fps を記録する', async ({ browser }) => {
  test.setTimeout(900_000);

  const entries: PerfEntry[] = [];
  for (const rate of RATES) {
    // 条件ごとに context を作り直す（スロットリングは CDP セッション単位のため分離が確実）
    const context: BrowserContext = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: DEVICE_SCALE_FACTOR,
    });
    const page = await setupCameraMock(context, 'stream');
    const cdp = await context.newCDPSession(page);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate });

    await startApp(page);
    // 初回フレームのアトラス生成・JIT を除外するため、数フレーム処理させてから計測する
    await waitForFrames(page, WARMUP_FRAMES, 300_000);
    const before = await readFrameStats(page);
    const t0 = Date.now();
    await page.waitForTimeout(MEASURE_MS);
    const after = await readFrameStats(page);
    const elapsed = (Date.now() - t0) / 1000;

    const snapshot = await page.evaluate(() => window.__bmTest!.getFpsSnapshot());
    const renderer = await page.evaluate(() => window.__bmTest!.getRenderer());
    expect(
      renderer,
      'WebGL2 がフォールバックせず使えていること（落ちていたら計測条件が変わる）',
    ).toBe('webgl2');

    const frames = after.frames - before.frames;
    const stageAvg = divideStages(subStages(after.stages, before.stages), frames);
    entries.push({
      rate,
      fps: frames / elapsed,
      frames,
      avgFps: snapshot.avgFps,
      minFps: snapshot.minFps,
      camFps: snapshot.camFps,
      stages: stageAvg,
      renderer,
    });
    console.log(`[perf] CPU ${rate}x: fps=${(frames / elapsed).toFixed(2)}（${frames} フレーム / ${elapsed.toFixed(1)} 秒）`);
    await context.close();
  }

  saveAndReport(entries);
});

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

/** 結果を JSON に保存し、前回実行との差分を表で表示する */
function saveAndReport(entries: PerfEntry[]): void {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.mkdirSync(HISTORY_DIR, { recursive: true });

  const previous = fs.existsSync(LATEST_PATH)
    ? (JSON.parse(fs.readFileSync(LATEST_PATH, 'utf8')) as { timestamp: string; entries: PerfEntry[] })
    : null;

  const timestamp = new Date().toISOString();
  const record = {
    timestamp,
    viewport: { ...VIEWPORT, deviceScaleFactor: DEVICE_SCALE_FACTOR },
    headless: false,
    note: 'GPU は実機ではないため絶対値ではなく前回との相対比較に使う。fps は累積カウンタの差分から算出',
    entries,
  };
  fs.writeFileSync(
    path.join(HISTORY_DIR, `perf-${timestamp.replaceAll(':', '-')}.json`),
    JSON.stringify(record, null, 2),
  );
  fs.writeFileSync(LATEST_PATH, JSON.stringify(record, null, 2));

  console.log('\n=== 計測結果（headed / viewport 390x844 / dpr 2 / 入力 30fps 動画） ===');
  console.log('rate    fps    frames  | 参考(5秒窓): avgFps  minFps  camFps | ステージ別平均 ms: pre   read  feat   sel   draw');
  for (const e of entries) {
    console.log(
      `${String(e.rate).padEnd(7)} ${e.fps.toFixed(2).padEnd(6)} ${String(e.frames).padEnd(7)}| ` +
        `${e.avgFps.toFixed(1).padEnd(11)} ${e.minFps.toFixed(1).padEnd(7)} ${fmtNum(e.camFps).padEnd(9)}| ` +
        `${e.stages.pre.toFixed(1).padEnd(5)} ${e.stages.read.toFixed(1).padEnd(5)} ${e.stages.feat.toFixed(1).padEnd(6)} ` +
        `${e.stages.sel.toFixed(1).padEnd(5)} ${e.stages.draw.toFixed(1)}`,
    );
  }

  if (previous) {
    console.log(`\n=== 前回実行（${previous.timestamp}）との差分（fps ベース） ===`);
    console.log('rate    fps 変化');
    const prevByRate = new Map(previous.entries.map((e) => [e.rate, e]));
    for (const e of entries) {
      const prev = prevByRate.get(e.rate);
      if (!prev || !Number.isFinite(prev.fps) || prev.fps === 0 || e.frames === 0) {
        console.log(`${String(e.rate).padEnd(7)} (比較不能: フレームが止まっているか前回データ無し)`);
        continue;
      }
      console.log(`${String(e.rate).padEnd(7)} ${fmtDelta(e.fps, prev.fps)}`);
    }
    console.log('（fps が大きく下がっていたらリグレッションの疑い。揺らぎは数%程度出る）');
  } else {
    console.log('\n（前回実行が無いので差分表示は省略。次回実行から比較される）');
  }
}

function fmtNum(n: number | null): string {
  return n === null ? 'n/a' : n.toFixed(1);
}

function fmtDelta(current: number, previous: number): string {
  if (previous === 0) return 'n/a';
  const pct = ((current - previous) / previous) * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}
