import fs from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';
import {
  CLIP_PATH,
  STILL_PATH,
  ROOT,
  setupCameraMock,
  startApp,
  waitForFrames,
  pinSelectorAMode,
} from './helpers';

/**
 * 正しさの確認（出力が正常か）:
 * 1. 動画ストリームで描画が継続し、画面が黒/白一色でなく時間変化すること
 * 2. 固定フレーム（全フレーム同一の動画を入力）で WebGL2 / Canvas 2D の出力が
 *    基準画像と一致すること（基準画像は初回実行時に data/baselines/ へ自動保存する。
 *    環境依存のため git 管理しない）
 * 3. WebGL2 と Canvas 2D（基準実装、N-4）の出力差分を記録する
 *    （2 方式は完全一致しない前提。差分率を前回比で見るための記録）
 */

const RESULTS_DIR = path.join(ROOT, 'results', 'correctness');
const BASELINE_DIR = path.join(ROOT, 'data', 'baselines');

test.beforeAll(() => {
  for (const p of [CLIP_PATH, STILL_PATH]) {
    if (!fs.existsSync(p)) {
      throw new Error(
        `${p} がありません。ffmpeg で生成する必要があるため、npm run test:media を実行してください`,
      );
    }
  }
});

/** 動画ストリームモード: 描画が継続し、黒/白一色でなく、時間変化すること */
test('動画ストリームで描画が継続し、画面が更新される', async ({ context }) => {
  const page = await setupCameraMock(context, 'stream');
  await startApp(page);

  // フレームループが例外停止すると F-9 のエラー表示が出る（start screen は remove 済みなので
  // .start-error が存在したら異常）
  await waitForFrames(page, 3);
  expect(await page.locator('.start-error').count(), 'エラー表示が出ていないこと').toBe(0);

  // 出力が時間変化すること（動画が動いている → 処理される入力フレームも変わる）
  const shot1 = await canvasShot(page);
  await waitForFrames(page, (await frameCount(page)) + 3);
  const shot2 = await canvasShot(page);
  expect(Buffer.compare(shot1, shot2) !== 0, '出力が変化していること').toBeTruthy();

  // 真っ黒 / 真っ白でないこと（輝度のばらつきで判定）
  const png = PNG.sync.read(shot2);
  const stddev = pixelStddev(png);
  console.log(`[stat] 輝度の標準偏差 = ${stddev.toFixed(1)}`);
  expect(stddev, '出力が一色でないこと').toBeGreaterThan(10);
});

/** 固定フレームモード: WebGL2（既定）の出力を基準画像と比較する */
test('固定フレーム: WebGL2 出力が基準画像と一致する', async ({ context }) => {
  const page = await setupCameraMock(context, 'still');
  await startApp(page);
  // 基準画像は selectorA の出力で作られているため、既定の classic ではなく固定する
  await pinSelectorAMode(page);
  await expectRenderer(page, 'webgl2');
  // スクリーンショットは canvas 要素の全面を撮るため、オーバーレイ（fps 表示・設定パネル）
  // が写り込む。fps 表示は数字が実行ごとに変わるため、基準比較の前に必ず消す
  await page.locator('.settings-toggle').click();
  await ensureFpsOffWhilePanelOpen(page);
  await closeSettings(page);
  // 同一入力で数フレーム描かせてから撮る（入力が同一なので何フレーム目でも同じ出力になる）
  await waitForFrames(page, 3);
  await page.waitForTimeout(500);

  const shot = await canvasShot(page);
  compareWithBaseline('webgl2', shot, 0.01);
});

/** 固定フレームモード: 設定 UI で Canvas 2D に切り替え、基準画像と比較する */
test('固定フレーム: Canvas 2D 出力が基準画像と一致する', async ({ context }) => {
  const page = await setupCameraMock(context, 'still');
  await startApp(page);
  // 基準画像は selectorA の出力で作られているため、既定の classic ではなく固定する
  await pinSelectorAMode(page);
  const before = await frameCount(page);
  await switchRendererViaUi(page, 'canvas2d');
  await ensureFpsOffWhilePanelOpen(page);
  await closeSettings(page);
  await waitForFrames(page, before + 3);
  await page.waitForTimeout(500);

  const shot = await canvasShot(page);
  compareWithBaseline('canvas2d', shot, 0.01);
});

/**
 * 2 方式の出力差分を記録する（N-4 の基準実装比較）。
 * 2 方式は同じグリッド・同じ入力から同じ文字を選んでも、描画の実装が違うため
 * pixel レベルでは一致しない（実測: この入力で約 57%の画素が閾値以上で異なる。
 * 毎回決定的に同じ値になるので、前回記録との一致で「どちらかの描画が変わった」
 * ことを検知できる。固定の閾値では判定しない）
 */
test('WebGL2 と Canvas 2D の出力差分を記録する', async () => {
  const webgl = PNG.sync.read(fs.readFileSync(path.join(RESULTS_DIR, 'webgl2.png')));
  const canvas = PNG.sync.read(fs.readFileSync(path.join(RESULTS_DIR, 'canvas2d.png')));
  expect(webgl.width, '比較対象のサイズが一致すること').toBe(canvas.width);
  expect(webgl.height, '比較対象のサイズが一致すること').toBe(canvas.height);

  const diff = new PNG({ width: webgl.width, height: webgl.height });
  const mismatched = pixelmatch(webgl.data, canvas.data, diff.data, webgl.width, webgl.height, {
    threshold: 0.1,
  });
  const ratio = mismatched / (webgl.width * webgl.height);
  fs.writeFileSync(path.join(RESULTS_DIR, 'renderer-diff.png'), PNG.sync.write(diff));
  console.log(`[compare] WebGL2 vs Canvas 2D: 差分 ${(ratio * 100).toFixed(3)}%`);

  const recordPath = path.join(RESULTS_DIR, 'cross-renderer.json');
  const previous = fs.existsSync(recordPath)
    ? (JSON.parse(fs.readFileSync(recordPath, 'utf8')) as { timestamp: string; ratio: number })
    : null;
  if (previous && Number.isFinite(previous.ratio)) {
    const delta = Math.abs(ratio - previous.ratio);
    console.log(
      `[compare] 前回（${previous.timestamp}）: ${(previous.ratio * 100).toFixed(3)}% → ` +
        `今回: ${(ratio * 100).toFixed(3)}%（差 ${((delta) * 100).toFixed(3)}pt）`,
    );
    expect(
      delta,
      '2 方式の差分率が前回とほぼ同じこと（ずれたらどちらかの描画が変わっている）',
    ).toBeLessThan(0.005);
  } else {
    console.log('[compare] 前回記録が無いので今回の値を基準にします（次回から比較される）');
  }
  fs.writeFileSync(
    recordPath,
    JSON.stringify({ timestamp: new Date().toISOString(), ratio, previous }, null, 2),
  );
});

async function canvasShot(page: Page): Promise<Buffer> {
  return page.locator('canvas.ascii-canvas').screenshot();
}

async function frameCount(page: Page): Promise<number> {
  return page.evaluate(() => window.__bmTest?.getFrameStats().frames ?? 0);
}

async function expectRenderer(page: Page, expected: string): Promise<void> {
  await page.waitForFunction(
    (value) => window.__bmTest?.getRenderer() === value,
    expected,
    { timeout: 30_000 },
  );
}

/** 設定パネル UI で描画方式を切り替える（本番の操作フローを通す） */
async function switchRendererViaUi(page: Page, value: string): Promise<void> {
  await page.locator('.settings-toggle').click();
  // 1 番目の select = 描画方式（2 番目は文字選択方式。mode）
  await page.locator('.settings-panel select').first().selectOption(value);
  await expectRenderer(page, value);
}

/**
 * fps 表示を OFF にする（設定パネルの最後のチェックボックス = fps 表示）。
 * ラベルは i18n 依存のため文言ではなく位置で特定する。パネルが開いている状態で呼ぶ。
 * fps 表示は数字が実行ごとに変わるため、基準画像比較のノイズになる。
 */
async function ensureFpsOffWhilePanelOpen(page: Page): Promise<void> {
  const checkbox = page.locator('.settings-panel input[type=checkbox]').last();
  if (await checkbox.isChecked()) {
    await checkbox.click();
  }
}

/** 設定パネルを閉じる（開いたままだとオーバーレイとして canvas に写り込むため） */
async function closeSettings(page: Page): Promise<void> {
  await page.locator('.settings-toggle').click();
  await expect(page.locator('.settings-panel')).toBeHidden();
}

/**
 * 基準画像との比較。基準が無い（またはサイズが変わった）場合は今回の結果を
 * 新しい基準として保存して合格にする（初回実行・環境変更時の挙動）。
 * 差分率は results/correctness/<name>-diff.png としても保存する。
 */
function compareWithBaseline(name: string, shot: Buffer, maxRatio: number): void {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.mkdirSync(BASELINE_DIR, { recursive: true });
  const actualPath = path.join(RESULTS_DIR, `${name}.png`);
  const baselinePath = path.join(BASELINE_DIR, `${name}.png`);
  fs.writeFileSync(actualPath, shot);

  const actual = PNG.sync.read(shot);
  if (!fs.existsSync(baselinePath)) {
    fs.writeFileSync(baselinePath, shot);
    console.log(`[baseline] ${name}: 基準画像が無いので新規保存しました（${actual.width}x${actual.height}）`);
    return;
  }

  const baseline = PNG.sync.read(fs.readFileSync(baselinePath));
  if (baseline.width !== actual.width || baseline.height !== actual.height) {
    fs.writeFileSync(baselinePath, shot);
    console.log(
      `[baseline] ${name}: サイズが変わったため基準を作り直しました ` +
        `(${baseline.width}x${baseline.height} -> ${actual.width}x${actual.height})`,
    );
    return;
  }

  const diff = new PNG({ width: actual.width, height: actual.height });
  const mismatched = pixelmatch(actual.data, baseline.data, diff.data, actual.width, actual.height, {
    threshold: 0.1,
  });
  const ratio = mismatched / (actual.width * actual.height);
  fs.writeFileSync(path.join(RESULTS_DIR, `${name}-diff.png`), PNG.sync.write(diff));
  console.log(`[compare] ${name}: 基準との差分 ${(ratio * 100).toFixed(3)}%（許容 < ${maxRatio * 100}%）`);
  expect(ratio, `${name} の出力が基準画像とほぼ一致すること`).toBeLessThan(maxRatio);
}

/** 輝度（0..255）の標準偏差。一色（真っ黒/白）なら 0 に近くなる */
function pixelStddev(png: PNG): number {
  const n = png.width * png.height;
  let sum = 0;
  let sum2 = 0;
  for (let i = 0; i < n; i++) {
    const y = 0.299 * png.data[i * 4] + 0.587 * png.data[i * 4 + 1] + 0.114 * png.data[i * 4 + 2];
    sum += y;
    sum2 += y * y;
  }
  const mean = sum / n;
  return Math.sqrt(sum2 / n - mean * mean);
}
