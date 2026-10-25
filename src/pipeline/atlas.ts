import type { AppConfig } from '../config';

/**
 * グリフアトラス（architecture.md §4）。
 *
 * 実行時はフォントではなくアトラス画像を転写して描画する（N-1, N-5）。
 * 将来は Python トラックが生成した public/assets のアトラス（PNG）と
 * 特徴量テーブル（JSON、D-002）を読む実装に差し替える。
 */

/** アトラス上の 1 グリフぶんの情報 */
export type GlyphInfo = {
  /** アトラス上の ID（= 描画時のセルインデックス） */
  id: number;
  /** 文字（1 文字） */
  char: string;
  /** 濃度（平均インク率 0..1）。将来は特徴量テーブル JSON から供給する（D-002） */
  ink: number;
};

/** 前景の色ごとに用意したアトラス画像 */
export type FgColor = 'black' | 'white';

export type GlyphAtlas = {
  charset: string;
  cellWidth: number;
  cellHeight: number;
  /** 全グリフ。id = 配列のインデックス */
  glyphs: GlyphInfo[];
  /** 濃度用のグリフ ID（ink 昇順 = 薄い順） */
  densityIds: number[];
  /** 線記号のグリフ ID（エッジ用）。見つからない場合は -1 */
  lineIds: {
    horizontal: number; // ―
    vertical: number; // ｜
    slash: number; // ／
    backslash: number; // ＼
  };
  /** 転写元のアトラス画像（前景色ごと） */
  canvasFor(fg: FgColor): HTMLCanvasElement;
};

export interface AtlasProvider {
  getAtlas(cfg: AppConfig): GlyphAtlas;
}

/**
 * 【ダミー実装】コード内にハードコードした全角文字の小さなセットを、
 * 起動時に（DOM 外の）canvas へ fillText で描いてアトラス代わりにする。
 *
 * - 本物のグリフアトラス資産は Python トラックから後日届く（public/assets 生成予定）
 * - このモジュール（AtlasProvider の実装）だけを差し替えれば、
 *   FeatureExtractor / GlyphSelector / Renderer は無変更で本物のアトラスに移行できる
 * - 濃度（インク率）はここで各文字を描いて測っている。これも将来 JSON から供給する値に置き換わる
 */
const DUMMY_CHARSETS: Record<string, { density: string[]; lines: string[] }> = {
  // 濃度用: 薄い順に並べたつもの候補（実際の並び順は描いて測ったインク率で決める）
  // 線用: エッジの向きに合わせて選ぶ線記号（T-5 の `／＼｜―` 系）
  default: {
    density: ['　', '・', '○', '＋', 'の', '三', '日', '◎', '■'],
    lines: ['―', '／', '｜', '＼'],
  },
};

const ATLAS_CELL = 96; // アトラス 1 セルのピクセル数（転写時に拡大縮小される）
const FONT_FAMILY = `"Noto Sans JP", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", Meiryo, sans-serif`;

/** アトラス画像は DOM に追加しない（画面に出ない canvas）で生成する */
function createOffscreenCanvas(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function drawGlyphCell(
  ctx: CanvasRenderingContext2D,
  char: string,
  cellX: number,
  color: string,
  cell = ATLAS_CELL,
): void {
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `${Math.floor(cell * 0.86)}px ${FONT_FAMILY}`;
  ctx.fillText(char, cellX + cell / 2, cell / 2);
}

/** 1 文字の平均インク率を測る（黒で描いてアルファの平均を取る） */
function measureInk(char: string): number {
  const size = 64;
  const canvas = createOffscreenCanvas(size, size);
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return 0;
  drawGlyphCell(ctx, char, 0, '#000000', size);
  const data = ctx.getImageData(0, 0, size, size).data;
  let sum = 0;
  for (let i = 3; i < data.length; i += 4) sum += data[i];
  return sum / (255 * size * size);
}

export class DummyAtlasProvider implements AtlasProvider {
  private cache = new Map<string, GlyphAtlas>();

  getAtlas(cfg: AppConfig): GlyphAtlas {
    let atlas = this.cache.get(cfg.charset);
    if (!atlas) {
      atlas = buildDummyAtlas(cfg.charset);
      this.cache.set(cfg.charset, atlas);
    }
    return atlas;
  }
}

export function buildDummyAtlas(charset: string): GlyphAtlas {
  const def = DUMMY_CHARSETS[charset] ?? DUMMY_CHARSETS['default'];

  // グリフの一覧を作る（重複はまとめる）
  const chars: string[] = [];
  for (const c of [...def.density, ...def.lines]) {
    if (!chars.includes(c)) chars.push(c);
  }
  const idOf = new Map<string, number>();
  const glyphs: GlyphInfo[] = chars.map((char, id) => {
    idOf.set(char, id);
    return { id, char, ink: measureInk(char) };
  });

  // 濃度用は測ったインク率の昇順（薄い順）に並べ直す
  const densityIds = def.density
    .map((c) => idOf.get(c) ?? -1)
    .filter((id) => id >= 0)
    .sort((a, b) => glyphs[a].ink - glyphs[b].ink);

  const lineIds = {
    horizontal: idOf.get('―') ?? -1,
    vertical: idOf.get('｜') ?? -1,
    slash: idOf.get('／') ?? -1,
    backslash: idOf.get('＼') ?? -1,
  };

  // 前景色ごとのアトラス画像を用意する（既定: 白背景＋黒文字、invert で反転。T-6）
  const canvases = new Map<FgColor, HTMLCanvasElement>();
  const canvasFor = (fg: FgColor): HTMLCanvasElement => {
    let canvas = canvases.get(fg);
    if (!canvas) {
      canvas = createOffscreenCanvas(ATLAS_CELL * glyphs.length, ATLAS_CELL);
      const ctx = canvas.getContext('2d');
      if (ctx) {
        const color = fg === 'black' ? '#000000' : '#ffffff';
        glyphs.forEach((g) => drawGlyphCell(ctx, g.char, g.id * ATLAS_CELL, color));
      }
      canvases.set(fg, canvas);
    }
    return canvas;
  };

  return {
    charset,
    cellWidth: ATLAS_CELL,
    cellHeight: ATLAS_CELL,
    glyphs,
    densityIds,
    lineIds,
    canvasFor,
  };
}
