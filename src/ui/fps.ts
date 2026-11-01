import { t } from '../i18n';
import { el } from './dom';

/** 1 フレームのステージ別処理時間（ms）。P-3 のデバッグ表示用 */
export type StageTimings = {
  /** 前処理 blit（video → work canvas の drawImage） */
  pre: number;
  /** 前処理読み出し（getImageData） */
  read: number;
  /** 特徴量計算（extract） */
  feat: number;
  /** 文字選択（select） */
  sel: number;
  /** 描画（render） */
  draw: number;
};

/** ローリング窓に溜める 1 フレームぶんのサンプル */
type FpsSample = {
  /** タイムスタンプ（ms。rAF / rVFC の now と同じ時刻系） */
  time: number;
  /** 瞬間値 1000/dt */
  fps: number;
  /** rVFC の metadata.presentedFrames（無い環境では null） */
  presentedFrames: number | null;
  /** ステージ別処理時間（映像がまだ用意できていないフレームでは null） */
  stages: StageTimings | null;
};

/** ローリング窓 1 回分の統計（P-3 の表示内容） */
export type FpsSnapshot = {
  /** 窓内の瞬間 fps の平均 */
  avgFps: number;
  /** 窓内の瞬間 fps の最小 */
  minFps: number;
  /** カメラ実効 fps（presentedFrames の差分から算出。metadata 無しでは null） */
  camFps: number | null;
  /** ステージ別の窓内平均処理時間（ms） */
  stages: StageTimings;
};

/** 統計を取る窓の長さ（ms）: 直近 5 秒 */
const WINDOW_MS = 5000;

/**
 * 直近 5 秒のローリング窓で fps とステージ別処理時間の統計を取る（P-3）。
 * EMA ではなく窓内の瞬間値（1000/dt）から平均・最小を求める。
 */
export class FpsStats {
  private samples: FpsSample[] = [];

  /** 1 フレームぶん追加する。presentedFrames は rVFC 環境でのみ渡す */
  add(
    time: number,
    fps: number,
    presentedFrames: number | null,
    stages: StageTimings | null,
  ): void {
    this.samples.push({ time, fps, presentedFrames, stages });
    // 窓の外の古いサンプルを落とす
    const cutoff = time - WINDOW_MS;
    while (this.samples.length > 0 && this.samples[0].time < cutoff) {
      this.samples.shift();
    }
  }

  /** 長い停止（タブの非表示など）をはさんだときに窓を立て直す */
  clear(): void {
    this.samples.length = 0;
  }

  snapshot(): FpsSnapshot {
    const emptyStages: StageTimings = { pre: 0, read: 0, feat: 0, sel: 0, draw: 0 };
    const samples = this.samples;
    if (samples.length === 0) {
      return { avgFps: 0, minFps: 0, camFps: null, stages: emptyStages };
    }

    let fpsSum = 0;
    let minFps = Infinity;
    let stageCount = 0;
    const stageSum: StageTimings = { pre: 0, read: 0, feat: 0, sel: 0, draw: 0 };
    for (const s of samples) {
      fpsSum += s.fps;
      if (s.fps < minFps) minFps = s.fps;
      if (s.stages) {
        stageCount++;
        stageSum.pre += s.stages.pre;
        stageSum.read += s.stages.read;
        stageSum.feat += s.stages.feat;
        stageSum.sel += s.stages.sel;
        stageSum.draw += s.stages.draw;
      }
    }

    // カメラ実効 fps は presentedFrames の差分を窓の経過時間で割る
    const first = samples[0];
    const last = samples[samples.length - 1];
    const camFps =
      first.presentedFrames !== null &&
      last.presentedFrames !== null &&
      last.presentedFrames > first.presentedFrames &&
      last.time > first.time
        ? ((last.presentedFrames - first.presentedFrames) * 1000) / (last.time - first.time)
        : null;

    const stages: StageTimings =
      stageCount > 0
        ? {
            pre: stageSum.pre / stageCount,
            read: stageSum.read / stageCount,
            feat: stageSum.feat / stageCount,
            sel: stageSum.sel / stageCount,
            draw: stageSum.draw / stageCount,
          }
        : emptyStages;

    return { avgFps: fpsSum / samples.length, minFps, camFps, stages };
  }
}

/** デバッグ用の統計オーバーレイ（P-3）。showFps の ON/OFF で表示を切り替える */
export type FpsIndicator = {
  update(snapshot: FpsSnapshot, columns: number, renderMethod: string): void;
  setVisible(visible: boolean): void;
};

export function createFpsIndicator(root: HTMLElement): FpsIndicator {
  const node = el('div', 'fps-indicator');
  node.hidden = true;
  root.append(node);
  let last = '';
  return {
    update(snapshot, columns, renderMethod): void {
      // 表記は言語依存の整形を避け、文言側で組み立てる（architecture.md §12）
      const cam =
        snapshot.camFps === null
          ? t('fpsNotAvailable')
          : `${snapshot.camFps.toFixed(1)} ${t('fpsLabel')}`;
      const rows = [
        `${t('fpsAvg')} ${snapshot.avgFps.toFixed(1)} ${t('fpsLabel')}`,
        `${t('fpsMin')} ${snapshot.minFps.toFixed(1)} ${t('fpsLabel')}`,
        `${t('fpsCam')} ${cam}`,
        `${t('fpsPre')} ${snapshot.stages.pre.toFixed(1)} ${t('msLabel')}`,
        `${t('fpsRead')} ${snapshot.stages.read.toFixed(1)} ${t('msLabel')}`,
        `${t('fpsFeat')} ${snapshot.stages.feat.toFixed(1)} ${t('msLabel')}`,
        `${t('fpsSel')} ${snapshot.stages.sel.toFixed(1)} ${t('msLabel')}`,
        `${t('fpsDraw')} ${snapshot.stages.draw.toFixed(1)} ${t('msLabel')}`,
        `${t('fpsCols')} ${columns} / ${renderMethod}`,
      ];
      const text = rows.join('\n');
      if (text !== last) {
        last = text;
        node.textContent = text;
      }
    },
    setVisible(visible): void {
      node.hidden = !visible;
    },
  };
}
