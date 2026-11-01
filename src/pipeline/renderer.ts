import type { AppConfig } from '../config';
import type { AtlasProvider, FgColor, GlyphAtlas } from './atlas';
import type { Renderer, GridSpec } from './types';

/**
 * 描画: Canvas 2D でグリフアトラスからセルごとに drawImage 転写する
 * （D-004 の先行実装。EXP-1 で WebGL2 版と比較する）。
 * 配色既定は白背景＋黒文字、invert で反転（T-6）。
 *
 * EXP-1 の基準測定では draw が最大のボトルネックで、原因は 96px のアトラスセルから
 * 出力セル（数十 px）への毎フレームの縮小転写。そのためセルの実サイズに縮小した
 * アトラスをキャッシュし、毎フレームの転写をほぼ等倍に留める（描画方式は Canvas 2D のまま）。
 * キャッシュはセルサイズ・invert・charset（= アトラスの中身）が変わったときだけ作り直す。
 * 縮小をキャッシュ生成時に 1 回で済ませる関係でフィルタの過程が毎フレーム縮小だった頃と
 * 変わり、グリフの見た目がわずかに変わることがある（EXP-1 では許容とする）。
 */
export class Canvas2DRenderer implements Renderer {
  /** 描画方式の名前（EXP-1 の計測表示用。Renderer インターフェースのシグネチャは変えない） */
  readonly renderMethod = 'canvas2d';

  /** 同一 canvas から得られる 2d コンテキストは不変なので初回だけ取得する */
  private ctx: CanvasRenderingContext2D | null = null;

  /** セル実サイズに縮小したアトラスのキャッシュ（作り直し条件とセットで持つ） */
  private cacheCanvas: HTMLCanvasElement | null = null;
  private cacheAtlas: GlyphAtlas | null = null;
  private cacheKey = '';
  private cacheCellW = 0;
  private cacheCellH = 0;

  constructor(
    private canvas: HTMLCanvasElement,
    private atlasProvider: AtlasProvider,
  ) {}

  render(glyphIds: Uint16Array, grid: GridSpec, cfg: AppConfig, _color?: Uint8Array): void {
    const ctx = this.ensureContext();
    if (!ctx) return;
    const atlas = this.atlasProvider.getAtlas(cfg);
    const src = this.scaledAtlas(atlas, cfg, grid);
    const cellW = this.cacheCellW;
    const cellH = this.cacheCellH;

    // 背景（文字を置かない部分）は全角スペース扱いで、背景色の塗りつぶしで済ませる（T-3）
    ctx.fillStyle = cfg.invert ? '#000000' : '#ffffff';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    const { cols, rows, cellWidth, cellHeight } = grid;

    // 小数端数による描き残り・すき間を避けるため、セル境界を四捨五入して確定させる
    const xs = new Int32Array(cols + 1);
    for (let x = 0; x <= cols; x++) xs[x] = Math.round(x * cellWidth);
    const ys = new Int32Array(rows + 1);
    for (let y = 0; y <= rows; y++) ys[y] = Math.round(y * cellHeight);

    for (let y = 0; y < rows; y++) {
      const dy = ys[y];
      const dh = ys[y + 1] - dy;
      for (let x = 0; x < cols; x++) {
        const id = glyphIds[y * cols + x];
        const glyph = atlas.glyphs[id];
        if (!glyph || glyph.ink < 0.01) continue; // ほぼ空白（全角スペース等）は塗らない
        const dx = xs[x];
        const dw = xs[x + 1] - dx;
        // 転写元はセル実サイズのキャッシュ。端数処理の差で ±1px の伸縮が残ることがある
        ctx.drawImage(src, id * cellW, 0, cellW, cellH, dx, dy, dw, dh);
      }
    }
  }

  private ensureContext(): CanvasRenderingContext2D | null {
    if (!this.ctx) this.ctx = this.canvas.getContext('2d');
    return this.ctx;
  }

  /**
   * セルの実サイズ（整数 px）に縮小したアトラスを作る。格子の端数による
   * セル幅の ±1px ぶんの伸縮は描画時の drawImage に任せる。
   */
  private scaledAtlas(atlas: GlyphAtlas, cfg: AppConfig, grid: GridSpec): HTMLCanvasElement {
    const cellW = Math.max(1, Math.round(grid.cellWidth));
    const cellH = Math.max(1, Math.round(grid.cellHeight));
    const fg: FgColor = cfg.invert ? 'white' : 'black';
    const key = `${cfg.charset}/${fg}/${cellW}x${cellH}`;
    if (this.cacheCanvas && this.cacheAtlas === atlas && this.cacheKey === key) {
      return this.cacheCanvas;
    }

    // 96px のアトラス列全体をセル実サイズへ一括で縮小する（高品質フィルタはここで 1 回だけ）
    const canvas = document.createElement('canvas');
    canvas.width = cellW * atlas.glyphs.length;
    canvas.height = cellH;
    const cctx = canvas.getContext('2d');
    if (cctx) {
      cctx.imageSmoothingEnabled = true;
      cctx.imageSmoothingQuality = 'high';
      cctx.drawImage(
        atlas.canvasFor(fg),
        0,
        0,
        atlas.cellWidth * atlas.glyphs.length,
        atlas.cellHeight,
        0,
        0,
        canvas.width,
        canvas.height,
      );
    }

    this.cacheCanvas = canvas;
    this.cacheAtlas = atlas;
    this.cacheKey = key;
    this.cacheCellW = cellW;
    this.cacheCellH = cellH;
    return canvas;
  }
}
