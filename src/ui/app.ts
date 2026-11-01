import type { AppConfig } from '../config';
import { CameraSource, type CameraErrorCode } from '../camera/camera';
import { startFrameLoop } from '../camera/frameLoop';
import { DummyAtlasProvider } from '../pipeline/atlas';
import { CpuFeatureExtractor } from '../pipeline/featureExtractor';
import { computeGrid } from '../pipeline/grid';
import { sampleFrame } from '../pipeline/preprocess';
import { Canvas2DRenderer } from '../pipeline/renderer';
import { DensityEdgeGlyphSelector } from '../pipeline/glyphSelector';
import { type MessageKey } from '../i18n';
import { createFpsIndicator, FpsStats, type FpsIndicator, type StageTimings } from './fps';
import { createSettingsPanel } from './settingsPanel';
import { createStartScreen, type StartScreen } from './startScreen';
import { el } from './dom';

/**
 * 画面フロー（requirements.md §7.1）の制御と、
 * 前処理 → 特徴量 → 文字選択 → 描画 のループ（architecture.md §2）。
 */
export class App {
  private video: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private workCanvas: HTMLCanvasElement | null = null;
  private fps: FpsIndicator | null = null;
  private stopLoop: (() => void) | null = null;
  private lastFrameTime = 0;
  private readonly fpsStats = new FpsStats();

  private readonly atlasProvider = new DummyAtlasProvider();
  private readonly extractor = new CpuFeatureExtractor();
  private readonly selector: DensityEdgeGlyphSelector;

  constructor(
    private root: HTMLElement,
    private cfg: AppConfig,
  ) {
    this.selector = new DensityEdgeGlyphSelector(this.atlasProvider);
  }

  showStart(): void {
    const screen = createStartScreen(this.root, () => {
      void this.begin(screen);
    });
  }

  /** 取得と描画ループを止める（ページ遷移などの終了時に呼べるように公開している） */
  stop(): void {
    this.stopLoop?.();
    this.stopLoop = null;
    const video = this.video;
    if (video) {
      const stream = video.srcObject as MediaStream | null;
      stream?.getTracks().forEach((track) => track.stop());
    }
  }

  private async begin(screen: StartScreen): Promise<void> {
    screen.setStarting();
    try {
      const video = await new CameraSource().start();
      this.video = video;
      screen.remove();
      this.runMain(video);
    } catch (e) {
      screen.showError(toMessageKey(e));
    }
  }

  private runMain(video: HTMLVideoElement): void {
    // video 要素は表示しないが、iOS Safari でデコードが止まらないよう実体は残す
    video.className = 'hidden-video';
    this.root.append(video);

    const canvas = el('canvas', 'ascii-canvas');
    this.root.append(canvas);
    this.canvas = canvas;
    this.workCanvas = document.createElement('canvas');

    // 設定パネル（F-6）と fps 表示（P-3）
    createSettingsPanel(this.root, this.cfg);
    this.fps = createFpsIndicator(this.root);

    const renderer = new Canvas2DRenderer(canvas, this.atlasProvider);
    this.stopLoop = startFrameLoop(video, (now, metadata) => {
      this.tick(now, metadata, renderer);
    });
  }

  private tick(
    now: number,
    metadata: VideoFrameCallbackMetadata | null,
    renderer: Canvas2DRenderer,
  ): void {
    const video = this.video;
    const canvas = this.canvas;
    const work = this.workCanvas;
    if (!video || !canvas || !work) return;

    const dt = now - this.lastFrameTime;
    this.lastFrameTime = now;

    // canvas の実サイズを表示サイズと dpr に追従させる（画面回転時も毎フレーム再計算。E-4）
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetW = Math.max(1, Math.round(canvas.clientWidth * dpr));
    const targetH = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== targetW) canvas.width = targetW;
    if (canvas.height !== targetH) canvas.height = targetH;

    const grid = computeGrid(canvas.width, canvas.height, this.cfg.columns);
    const sampled = sampleFrame(video, grid, work);

    // ステージ別の処理時間を計測する（P-3）。前処理 blit / read は sampleFrame が測る
    let stages: StageTimings | null = null;
    if (sampled.frame) {
      stages = { pre: sampled.timings.pre, read: sampled.timings.read, feat: 0, sel: 0, draw: 0 };
      const extractStart = performance.now();
      const features = this.extractor.extract(sampled.frame, grid, this.cfg);
      const selectStart = performance.now();
      const glyphIds = this.selector.select(features, this.cfg);
      const renderStart = performance.now();
      renderer.render(glyphIds, grid, this.cfg);
      stages.feat = selectStart - extractStart;
      stages.sel = renderStart - selectStart;
      stages.draw = performance.now() - renderStart;
    }

    // fps 統計（P-3）: EMA ではなく直近 5 秒のローリング窓で平均・最小を取る。
    // タブの非表示などで長く止まっていたフレームは瞬間値が極端になるため窓を立て直す
    if (dt > 0 && dt < 1000) {
      this.fpsStats.add(now, 1000 / dt, metadata ? metadata.presentedFrames : null, stages);
    } else {
      this.fpsStats.clear();
    }

    if (this.fps) {
      this.fps.setVisible(this.cfg.showFps);
      this.fps.update(this.fpsStats.snapshot(), this.cfg.columns, renderer.renderMethod);
    }
  }
}

/** CameraError（と予期しないエラー）を F-9 の文言キーへ写像する */
function toMessageKey(e: unknown): MessageKey {
  const code: CameraErrorCode | 'unknown' =
    e instanceof Error && 'code' in e ? (e.code as CameraErrorCode) : 'unknown';
  switch (code) {
    case 'permissionDenied':
      return 'errorPermissionDenied';
    case 'cameraNotFound':
      return 'errorCameraNotFound';
    case 'cameraBusy':
      return 'errorCameraBusy';
    case 'unsupported':
      return 'errorUnsupported';
    default:
      return 'errorUnknown';
  }
}
