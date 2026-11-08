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

/** 方式 A のエッジ置換で使う「まっすぐな線」のグリフ（D-009 / T-5） */
export type StraightLineGlyph = {
  id: number;
  /** 線の向き（度。0 = ― 水平、45 = ＼、90 = ｜ 垂直、135 = ／。画面座標系・y 下向き） */
  angleDeg: number;
  /** 濃度（平均インク率 0..1）。エッジの強さで太さ（濃度）を選ぶのに使う */
  ink: number;
};

export type GlyphAtlas = {
  charset: string;
  cellWidth: number;
  cellHeight: number;
  /** 全グリフ。id = 配列のインデックス */
  glyphs: GlyphInfo[];
  /** 濃度用のグリフ ID（ink 昇順 = 薄い順） */
  densityIds: number[];
  /** エッジ置換で使う直線グリフ（向き・濃度付き。角・T 字は向きが一意でないため含めない） */
  straightLines: StraightLineGlyph[];
  /** 転写元のアトラス画像（前景色ごと） */
  canvasFor(fg: FgColor): HTMLCanvasElement;
};

export interface AtlasProvider {
  getAtlas(cfg: AppConfig): GlyphAtlas;
}

/**
 * 【ダミー実装】コード内にハードコードした全角文字のセットを、
 * 起動時に（DOM 外の）canvas へ fillText で描いてアトラス代わりにする。
 *
 * - 文字セットは EXP-3（D-010 / T-4）で確定した採用セット
 *   （プリセット all = density 27 文字 + line 35 文字、計 62 文字）
 * - 本物のグリフアトラス資産は Python トラックが生成する（tools/prototype/atlas.py、
 *   Noto Sans JP Regular。public/assets 生成予定）。このモジュール（AtlasProvider の
 *   実装）だけを差し替えれば、FeatureExtractor / GlyphSelector / Renderer は無変更で移行できる
 * - 濃度（インク率）はここで各文字を描いて測っている。これも将来 JSON から供給する値に置き換わる
 *   （Noto Sans JP とシステムフォントの差で測定値は多少ずれる。実物資産に移行すれば解消）
 */
const DENSITY_CHARS = [
  '　', // 全角スペース（背景 = T-3）
  '・', // 中黒
  '：', // 全角コロン
  '∴', // ゆえに
  '◇', // 白ダイヤ
  '○', // 白丸
  '□', // 白四角
  '△', // 白三角
  '☆', // 白星
  '◎', // 二重丸
  '※', // こめじるし
  '▒', // 中網かけ（EXP-3 追加）
  '▣', // 白四角＋中黒四角（EXP-3 追加）
  '★', // 黒星
  '▃', // 下棒 3/8（EXP-3 追加）
  '◐', // 左半円（EXP-3 追加）
  '▲', // 黒三角
  '▄', // 下棒 1/2（EXP-3 追加）
  '◆', // 黒ダイヤ
  '▀', // 上棒 1/2（EXP-3 追加）
  '▅', // 下棒 5/8（EXP-3 追加）
  '●', // 黒丸
  '■', // 黒四角
  '▆', // 下棒 3/4（EXP-3 追加）
  '▛', // 上 3/4 ブロック（EXP-3 追加）
  '▇', // 下棒 7/8（EXP-3 追加）
  '█', // 全ブロック（EXP-3 追加。このフォントで最も濃い記号）
];

const LINE_CHARS = [
  '―', // 水平バー
  '─', '━', // 細線 / 太線（横）
  '│', '┃', // 細線 / 太線（縦）
  '┌', '┐', '└', '┘', // 細い角
  '├', '┤', '┬', '┴', '┼', // 細いT字・十字
  '┏', '┓', '┗', '┛', // 太い角
  '┣', '┫', '┳', '┻', '╋', // 太いT字・十字
  '═', '║', // 二重線
  '╭', '╮', '╯', '╰', // 丸角
  '╱', '╲', '╳', // 斜線
  '／', '＼', // 全角斜線
  '｜', // 全角縦棒
];

/**
 * 方式 A のエッジ置換で使う「まっすぐな線」と向き（度）。
 * 角・T 字・十字は向きが一意でないため候補から外す（D-009 / T-5 の調整に相当）。
 */
const STRAIGHT_LINES: ReadonlyArray<readonly [string, number]> = [
  ['―', 0], ['─', 0], ['━', 0], ['═', 0], // 水平
  ['│', 90], ['┃', 90], ['║', 90], ['｜', 90], // 垂直
  ['╲', 45], ['＼', 45], // バックスラッシュ
  ['╱', 135], ['／', 135], // スラッシュ
];

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
  // グリフの一覧を作る（重複はまとめる）
  const chars: string[] = [];
  for (const c of [...DENSITY_CHARS, ...LINE_CHARS]) {
    if (!chars.includes(c)) chars.push(c);
  }
  const idOf = new Map<string, number>();
  const glyphs: GlyphInfo[] = chars.map((char, id) => {
    idOf.set(char, id);
    return { id, char, ink: measureInk(char) };
  });

  // 濃度用は測ったインク率の昇順（薄い順）に並べ直す
  const densityIds = DENSITY_CHARS.map((c) => idOf.get(c) ?? -1)
    .filter((id) => id >= 0)
    .sort((a, b) => glyphs[a].ink - glyphs[b].ink);

  // エッジ置換用の直線グリフ（向きは STRAIGHT_LINES の定義、濃度は測定値）
  const straightLines: StraightLineGlyph[] = STRAIGHT_LINES
    .map(([char, angleDeg]) => {
      const id = idOf.get(char);
      return id === undefined ? null : { id, angleDeg, ink: glyphs[id].ink };
    })
    .filter((g): g is StraightLineGlyph => g !== null);

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
    straightLines,
    canvasFor,
  };
}
