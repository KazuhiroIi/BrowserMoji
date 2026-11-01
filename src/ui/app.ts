import type { AppConfig } from '../config';
import { CameraSource, type CameraErrorCode } from '../camera/camera';
import { startFrameLoop } from '../camera/frameLoop';
import { DummyAtlasProvider } from '../pipeline/atlas';
import { CpuFeatureExtractor } from '../pipeline/featureExtractor';
import { computeGrid } from '../pipeline/grid';
import { sampleFrame } from '../pipeline/preprocess';
import type { RendererKind } from '../config';
import { Canvas2DRenderer } from '../pipeline/renderer';
import { WebGL2Renderer, isWebGL2Available } from '../pipeline/rendererWebGL2';
import { DensityEdgeGlyphSelector } from '../pipeline/glyphSelector';
import { type MessageKey, t } from '../i18n';
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
  private canvas2dRenderer: Canvas2DRenderer | null = null;
  private webglRenderer: WebGL2Renderer | null = null;
  private fps: FpsIndicator | null = null;
  private stopLoop: (() => void) | null = null;
  private lastFrameTime = 0;
  private readonly fpsStats = new FpsStats();

  private readonly atlasProvider = new DummyAtlasProvider();
  private readonly extractor = new CpuFeatureExtractor();
  private readonly selector: DensityEdgeGlyphSelector;
  /** 現在使っている描画方式（cfg.renderer の選択・フォールバックの結果） */
  private activeRendererKind: RendererKind = 'canvas2d';
  /** WebGL2 が使えない / context lost になった後の再試行を防ぐフラグ */
  private webgl2Broken = false;

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
    createSettingsPanel(this.root, this.cfg, isWebGL2Available());
    this.fps = createFpsIndicator(this.root);

    this.stopLoop = startFrameLoop(video, (now, metadata) => {
      this.tick(now, metadata);
    });
  }

  /**
   * cfg.renderer の選択に合わせて描画方式を用意する（切替は次フレームから反映）。
   * 1 つの canvas には 1 種類のコンテキストしか取れないため、方式を変えるときは
   * canvas 要素を作り直して差し替える。WebGL2 が使えない / context lost の場合は
   * Canvas 2D にフォールバックし、オーバーレイの方式名が実態を反映する。
   * 初回フレームでは選択と実態が一致していても Renderer がまだ無いため、ここで生成する。
   */
  private ensureRenderer(): Canvas2DRenderer | WebGL2Renderer {
    // 描画方式の切替時と、選択に対応する Renderer がまだ無いとき（初回フレームなど）に生成する
    const missing =
      this.cfg.renderer === 'webgl2' ? this.webglRenderer === null : this.canvas2dRenderer === null;
    if (this.cfg.renderer !== this.activeRendererKind || missing) {
      const useWebGL2 = this.cfg.renderer === 'webgl2' && !this.webgl2Broken;
      if (!useWebGL2 && this.cfg.renderer === 'webgl2') {
        // 使えないと判明した後の再選択。再試行はしないので選択を Canvas 2D に戻す（E-2 と同じ扱い）
        this.cfg.renderer = 'canvas2d';
      }
      // 1 つの canvas に取れるコンテキストは 1 種類なので、WebGL2 を使っていた
      // canvas は Canvas 2D に切り替えるときにも作り直す必要がある
      const canvas =
        useWebGL2 || this.activeRendererKind === 'webgl2'
          ? this.replaceCanvas()
          : (this.canvas ?? this.replaceCanvas());
      if (useWebGL2) {
        try {
          this.webglRenderer = new WebGL2Renderer(canvas, this.atlasProvider);
        } catch {
          // 非対応環境: Canvas 2D にフォールバックし、選択も戻す（E-2）。
          // webgl2 コンテキストを取った canvas から 2d は取り直せないため canvas も作り直す
          this.webgl2Broken = true;
          this.cfg.renderer = 'canvas2d';
          this.canvas2dRenderer = new Canvas2DRenderer(this.replaceCanvas(), this.atlasProvider);
        }
      } else if (this.cfg.renderer === 'canvas2d') {
        // 2d コンテキストは同一 canvas から取得し直せる（失敗時の再利用もここで行う）
        this.canvas2dRenderer = new Canvas2DRenderer(canvas, this.atlasProvider);
      }
      this.activeRendererKind = this.cfg.renderer;
    }

    // 実行中の context lost を検知したら Canvas 2D にフォールバックする
    const webgl = this.webglRenderer;
    if (webgl?.isContextLost()) {
      const canvas = this.replaceCanvas();
      this.canvas2dRenderer = new Canvas2DRenderer(canvas, this.atlasProvider);
      this.webglRenderer = null;
      this.webgl2Broken = true;
      this.cfg.renderer = 'canvas2d';
      this.activeRendererKind = 'canvas2d';
      return this.canvas2dRenderer;
    }
    // 選択中の方式に対応する Renderer を返す。canvas2dRenderer が残っていても
    // こちらを優先しないと、切替後も古い Renderer が外れた canvas に描き続けてしまう
    return (this.activeRendererKind === 'webgl2' ? this.webglRenderer : this.canvas2dRenderer)!;
  }

  /** 新しい canvas 要素を既存のものと入れ替える（コンテキスト種別の変更時） */
  private replaceCanvas(): HTMLCanvasElement {
    const canvas = el('canvas', 'ascii-canvas');
    this.canvas?.replaceWith(canvas);
    this.canvas = canvas;
    return canvas;
  }

  private tick(now: number, metadata: VideoFrameCallbackMetadata | null): void {
    try {
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

      // 描画方式: cfg.renderer の選択に追従する（切替・フォールバックは次フレームから反映）
      const renderer = this.ensureRenderer();

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
    } catch (e) {
      // 例外を放置するとフレームループが止まったまま白画面になるため、
      // ここでループを停止して原因と対処を画面に表示する（F-9）。
      // 停止後の fps オーバーレイは古い値のままなので隠す
      this.stopLoop?.();
      this.stopLoop = null;
      this.fps?.setVisible(false);
      this.showLoopError(e);
    }
  }

  /** tick 内で回復できない例外が起きたときの表示（F-9。開始画面のエラー表示と同じ体裁で出す） */
  private showLoopError(e: unknown): void {
    const errorBox = el('div', 'start-error');
    errorBox.append(
      el('p', 'start-error-title', t('errorRenderLoopTitle')),
      el('p', undefined, t('errorRenderLoopBody')),
      // 開発者ツールの無い実機でも原因を報告できるように、例外の内容も添える
      el('p', undefined, String(e instanceof Error ? e.message : e)),
    );
    const screen = el('section', 'start-screen');
    screen.append(errorBox);
    this.root.append(screen);
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
