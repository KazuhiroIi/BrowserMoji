import type { AppConfig } from '../config';
import { CameraSource, type CameraErrorCode } from '../camera/camera';
import { startFrameLoop } from '../camera/frameLoop';
import { DummyAtlasProvider } from '../pipeline/atlas';
import { CpuFeatureExtractor } from '../pipeline/featureExtractor';
import { computeGrid } from '../pipeline/grid';
import { sampleFrame } from '../pipeline/preprocess';
import { Canvas2DRenderer } from '../pipeline/renderer';
import { DensityEdgeGlyphSelector } from '../pipeline/glyphSelector';
import type { FrameSource } from '../pipeline/types';
import { type MessageKey } from '../i18n';
import { createFpsIndicator, type FpsIndicator } from './fps';
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
  private fpsValue = 0;

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
    this.stopLoop = startFrameLoop(video, (now) => {
      this.tick(now, renderer);
    });
  }

  private tick(now: number, renderer: Canvas2DRenderer): void {
    const video = this.video;
    const canvas = this.canvas;
    const work = this.workCanvas;
    if (!video || !canvas || !work) return;

    // fps 計測（P-3）
    const dt = now - this.lastFrameTime;
    this.lastFrameTime = now;
    if (dt > 0 && dt < 1000) {
      this.fpsValue = this.fpsValue === 0 ? 1000 / dt : this.fpsValue * 0.9 + (1000 / dt) * 0.1;
    }

    // canvas の実サイズを表示サイズと dpr に追従させる（画面回転時も毎フレーム再計算。E-4）
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetW = Math.max(1, Math.round(canvas.clientWidth * dpr));
    const targetH = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== targetW) canvas.width = targetW;
    if (canvas.height !== targetH) canvas.height = targetH;

    const grid = computeGrid(canvas.width, canvas.height, this.cfg.columns);
    const frame: FrameSource | null = sampleFrame(video, grid, work);
    if (frame) {
      const features = this.extractor.extract(frame, grid, this.cfg);
      const glyphIds = this.selector.select(features, this.cfg);
      renderer.render(glyphIds, grid, this.cfg);
    }

    if (this.fps) {
      this.fps.setVisible(this.cfg.showFps);
      this.fps.update(this.fpsValue);
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
