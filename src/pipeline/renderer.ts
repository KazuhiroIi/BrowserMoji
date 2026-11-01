import type { AppConfig } from '../config';
import type { AtlasProvider } from './atlas';
import type { Renderer, GridSpec } from './types';

/**
 * 描画: Canvas 2D でグリフアトラスからセルごとに drawImage 転写する
 * （D-004 の先行実装。EXP-1 で WebGL2 版と比較する）。
 * 配色既定は白背景＋黒文字、invert で反転（T-6）。
 */
export class Canvas2DRenderer implements Renderer {
  /** 描画方式の名前（EXP-1 の計測表示用。Renderer インターフェースのシグネチャは変えない） */
  readonly renderMethod = 'canvas2d';

  constructor(
    private canvas: HTMLCanvasElement,
    private atlasProvider: AtlasProvider,
  ) {}

  render(glyphIds: Uint16Array, grid: GridSpec, cfg: AppConfig, _color?: Uint8Array): void {
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;
    const atlas = this.atlasProvider.getAtlas(cfg);

    // 背景（文字を置かない部分）は全角スペース扱いで、背景色の塗りつぶしで済ませる（T-3）
    ctx.fillStyle = cfg.invert ? '#000000' : '#ffffff';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    const src = atlas.canvasFor(cfg.invert ? 'white' : 'black');
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
        ctx.drawImage(
          src,
          id * atlas.cellWidth,
          0,
          atlas.cellWidth,
          atlas.cellHeight,
          dx,
          dy,
          dw,
          dh,
        );
      }
    }
  }
}
