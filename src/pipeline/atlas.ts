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
export type FgColor = 'black' | 'white' | 'green';

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
  /**
   * 線記号のグリフ ID（エッジ用。4 方向）。見つからない場合は -1。
   * classic モードの文字選択（ClassicGlyphSelector）が使う
   */
  lineIds: {
    horizontal: number; // ―
    vertical: number; // ｜
    slash: number; // ／
    backslash: number; // ＼
  };
  /** エッジ置換で使う直線グリフ（向き・濃度付き。角・T 字は向きが一意でないため含めない） */
  straightLines: StraightLineGlyph[];
  /** 転写元のアトラス画像（前景色ごと） */
  canvasFor(fg: FgColor): HTMLCanvasElement;
};

export interface AtlasProvider {
  /**
   * アトラスを返す。maxAtlasWidth を渡すと、アトラス 1 行の幅がその値以内に
   * 収まるようセル幅を縮めて構成する（WebGL2 のテクスチャ幅上限。D-011）。
   * 上限が極端に小さく収められない場合は例外を投げる（呼び出し側がフォールバックする）。
   */
  getAtlas(cfg: AppConfig, maxAtlasWidth?: number): GlyphAtlas;
}

/**
 * classic モード（076886d 適用前）の文字セット。EXP-2 / EXP-3 の適用（D-009 / D-010）
 * 前のダミーセット。履歴（076886d^ の atlas.ts の DUMMY_CHARSETS.default）から復元した
 */
const LEGACY_DENSITY_CHARS = [
  '　', // 全角スペース（背景 = T-3）
  '・', // 中黒
  '○', // 白丸
  '＋', // 全角プラス
  'の', // ひらがな「の」
  '三', // 漢字「三」
  '日', // 漢字「日」
  '◎', // 二重丸
  '■', // 黒四角
];

const LEGACY_LINE_CHARS = [
  '―', // 水平バー
  '／', // 全角斜線
  '｜', // 全角縦棒
  '＼', // 全角バックスラッシュ
];

/**
 * 【ダミー実装】コード内にハードコードした全角文字のセットを、
 * 起動時に（DOM 外の）canvas へ fillText で描いてアトラス代わりにする。
 *
 * - 文字セットは cfg.charset で選ぶ:
 *   - all: EXP-3（D-010 / T-4）で確定した採用セット
 *     （density 27 文字 + line 35 文字、計 62 文字）
 *   - default: classic モード用の旧セット（076886d 適用前。EXP-2 / EXP-3 適用前）
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

const ATLAS_CELL = 96; // アトラス 1 セルの基本ピクセル数（転写時に拡大縮小される。上限対応で縮めることがある。D-011）
const MIN_ATLAS_CELL = 16; // テクスチャ幅上限対応で縮めるセル幅の下限。これでも収まらなければ例外（Canvas 2D へフォールバック）
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

/** 指定 charset の既定フィラー文字セットを 1 つの文字列として返す */
export function getDefaultFillerChars(charset: string): string {
  const chars = charset === 'default' ? LEGACY_DENSITY_CHARS : DENSITY_CHARS;
  return chars.join('');
}

/** 入力文字列からフィラー文字の配列を作る（改行除去・重複除去・空欄時は全角スペース） */
function parseFillerChars(raw: string): string[] {
  const unique: string[] = [];
  for (const ch of Array.from(raw.replace(/[\r\n]/g, ''))) {
    if (!unique.includes(ch)) unique.push(ch);
  }
  return unique.length > 0 ? unique : ['　'];
}

export class DummyAtlasProvider implements AtlasProvider {
  private cache = new Map<string, GlyphAtlas>();

  getAtlas(cfg: AppConfig, maxAtlasWidth?: number): GlyphAtlas {
    const key = `${cfg.charset}/${cfg.fillerChars ?? ''}/${maxAtlasWidth ?? ''}`;
    let atlas = this.cache.get(key);
    if (!atlas) {
      if (this.cache.size > 20) this.cache.clear();
      atlas = buildDummyAtlas(cfg.charset, maxAtlasWidth, cfg.fillerChars);
      this.cache.set(key, atlas);
    }
    return atlas;
  }
}

export function buildDummyAtlas(
  charset: string,
  maxAtlasWidth?: number,
  fillerChars?: string | null,
): GlyphAtlas {
  // 文字セットは charset 値で選ぶ（unknown は all = 現行セットにフォールバック）
  const legacy = charset === 'default';
  const densityChars =
    fillerChars != null
      ? parseFillerChars(fillerChars)
      : legacy
        ? LEGACY_DENSITY_CHARS
        : DENSITY_CHARS;
  const lineChars = legacy ? LEGACY_LINE_CHARS : LINE_CHARS;
  const atlasCharset = fillerChars != null ? `${charset}:${fillerChars}` : charset;

  // グリフの一覧を作る（重複はまとめる）
  const chars: string[] = [];
  for (const c of [...densityChars, ...lineChars]) {
    if (!chars.includes(c)) chars.push(c);
  }

  /**
   * 1 セル幅。maxAtlasWidth（WebGL2 のテクスチャ幅上限など）を超えるときは
   * 1 セル幅を縮めて 1 行のアトラスに収める（D-011）。転写先の出力セルは
   * 多くても数十 px なので、66px などへの縮小は見た目にほぼ影響しない。
   */
  let cell = ATLAS_CELL;
  if (maxAtlasWidth !== undefined && chars.length * cell > maxAtlasWidth) {
    cell = Math.floor(maxAtlasWidth / chars.length);
    if (cell < MIN_ATLAS_CELL) {
      throw new Error(
        `アトラス（${chars.length} グリフ）をテクスチャ幅上限 ${maxAtlasWidth}px に収められない`,
      );
    }
  }

  const idOf = new Map<string, number>();
  const glyphs: GlyphInfo[] = chars.map((char, id) => {
    idOf.set(char, id);
    return { id, char, ink: measureInk(char) };
  });

  // 濃度用は測ったインク率の昇順（薄い順）に並べ直す
  const densityIds = densityChars.map((c) => idOf.get(c) ?? -1)
    .filter((id) => id >= 0)
    .sort((a, b) => glyphs[a].ink - glyphs[b].ink);

  // 4 方向の線記号（classic モードの文字選択が使う。見つからない場合は -1）
  const lineIds = {
    horizontal: idOf.get('―') ?? -1,
    vertical: idOf.get('｜') ?? -1,
    slash: idOf.get('／') ?? -1,
    backslash: idOf.get('＼') ?? -1,
  };

  // エッジ置換用の直線グリフ（向きは STRAIGHT_LINES の定義、濃度は測定値）
  const straightLines: StraightLineGlyph[] = STRAIGHT_LINES
    .map(([char, angleDeg]) => {
      const id = idOf.get(char);
      return id === undefined ? null : { id, angleDeg, ink: glyphs[id].ink };
    })
    .filter((g): g is StraightLineGlyph => g !== null);

  // 前景色ごとのアトラス画像を用意する（既定: 白背景＋黒文字、invert で反転。T-6）。
  // 背景も塗った**不透明**な canvas にする（D-011）。かつては透明背景＋文字だけを
  // 描き、WebGL2 シェーダ側で背景色と alpha で合成していたが、テクスチャ転送の
  // 失敗（不完全テクスチャは不透明黒を返す）や端末の alpha 取扱い差で黒画面になる
  // 要因になっていた。不透明にすればシェーダは tex.rgb をそのまま出力するだけでよい
  const canvases = new Map<FgColor, HTMLCanvasElement>();
  const canvasFor = (fg: FgColor): HTMLCanvasElement => {
    let canvas = canvases.get(fg);
    if (!canvas) {
      canvas = createOffscreenCanvas(cell * glyphs.length, cell);
      const ctx = canvas.getContext('2d');
      if (ctx) {
        const bgColor = fg === 'black' ? '#ffffff' : '#000000';
        const color = fg === 'black' ? '#000000' : fg === 'green' ? '#00ff41' : '#ffffff';
        ctx.fillStyle = bgColor;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        glyphs.forEach((g) => drawGlyphCell(ctx, g.char, g.id * cell, color, cell));
      }
      canvases.set(fg, canvas);
    }
    return canvas;
  };

  return {
    charset: atlasCharset,
    cellWidth: cell,
    cellHeight: cell,
    glyphs,
    densityIds,
    lineIds,
    straightLines,
    canvasFor,
  };
}
