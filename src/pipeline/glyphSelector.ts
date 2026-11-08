import type { AppConfig } from '../config';
import type { AtlasProvider, StraightLineGlyph } from './atlas';
import type { CellFeature, GlyphSelector } from './types';

/**
 * 文字選択 方式 A（EXP-2 で採用、docs/decisions/D-009-glyph-selector-a.md）:
 * 輝度で濃度文字を選ぶ。エッジセルは勾配の向きに最も近い直線の文字へ置き換える。
 * 基準実装（tools/prototype/selector.py の SelectorA.select）と同じ意味にする:
 *
 * 1. 濃度選択は等分量子化ではなく、アトラスで**計測した濃度**との最近傍
 *    （27 段階では量子化だとランプを無駄にする）
 * 2. エッジ検出はセル内最大 |勾配|、対象は整合性の高いセルのみ
 *    （境界を実際に含むセル。隣のセルは向きが打ち消し合うので除外）
 * 3. 線文字の選択は向きの最短角 + 勾配強度による太さ（濃度）選択
 *    （score = (Δangle / (π/8))² + 0.5 · Δdensity²）
 */
export class DensityEdgeGlyphSelector implements GlyphSelector {
  constructor(private atlasProvider: AtlasProvider) {}

  select(features: CellFeature[], cfg: AppConfig): Uint16Array {
    const atlas = this.atlasProvider.getAtlas(cfg);
    const densityIds = atlas.densityIds;
    const densityInk = densityIds.map((id) => atlas.glyphs[id].ink);
    const lines = atlas.straightLines;
    const ids = new Uint16Array(features.length);

    // edgePriority が大きいほど実効しきい値が下がる（= 置き替わりやすい）。
    // 既定 0.5 のとき edgeThreshold そのもの、0 で 1.5 倍、1 で 0.5 倍。
    const effectiveThreshold = cfg.edgeThreshold * (1.5 - clamp01(cfg.edgePriority));

    for (let i = 0; i < features.length; i++) {
      const f = features[i];
      const v = applyContrast(f.luminance, cfg.contrast);
      let id = pickDensity(densityIds, densityInk, 1 - v);

      // エッジ判定: セル内最大 |勾配|（EXP-2 発見 1）と整合性（D-009）
      if (f.gradMagnitude >= effectiveThreshold && f.gradCoherence >= cfg.coherenceMin) {
        id = pickLineGlyph(lines, f.gradAngle, f.gradMagnitude);
      }
      ids[i] = id;
    }
    return ids;
  }
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function applyContrast(v: number, contrast: number): number {
  return Math.min(1, Math.max(0, (v - 0.5) * contrast + 0.5));
}

/**
 * 濃度文字: ink 値（1 = 黒に近い）との最近傍を選ぶ。
 * densityIds は ink 昇順なので、挿入位置の前後で近い方を取る（searchsorted 相当）。
 */
function pickDensity(densityIds: number[], densityInk: number[], inkLevel: number): number {
  const n = densityIds.length;
  if (n === 1) return densityIds[0];
  // inkLevel < ink[0] の pos は 1 にクランプ（基準実装 np.searchsorted の clip と同じ）
  let pos = 1;
  while (pos < n && densityInk[pos] < inkLevel) pos++;
  if (pos >= n) pos = n - 1;
  const lo = pos - 1;
  return Math.abs(inkLevel - densityInk[lo]) <= Math.abs(inkLevel - densityInk[pos])
    ? densityIds[lo]
    : densityIds[pos];
}

/**
 * 線の向きは勾配の向き + 90°。0..π に正規化して、向きの最短角と
 * エッジ強度による濃度（太さ）の近さでスコアを付け、最小の線文字を選ぶ
 * （基準実装 SelectorA.select の score 式と同じ。T-5 の調整に相当）
 */
function pickLineGlyph(lines: StraightLineGlyph[], gradAngle: number, gradMagnitude: number): number {
  if (lines.length === 0) return -1;
  // 勾配の向きと直交する方向（0..π）に正規化する
  let deg = ((gradAngle + Math.PI / 2) * 180) / Math.PI;
  deg = deg % 180;
  if (deg < 0) deg += 180;
  const ang = (deg * Math.PI) / 180;

  const target = clamp01(gradMagnitude); // 弱いエッジ → 細い（薄い）線
  let best = lines[0].id;
  let bestScore = Infinity;
  for (const line of lines) {
    let d = Math.abs(ang - (line.angleDeg * Math.PI) / 180);
    d = Math.min(d, Math.PI - d); // 折り返し
    const score = (d / (Math.PI / 8)) ** 2 + 0.5 * (line.ink - target) ** 2;
    if (score < bestScore) {
      bestScore = score;
      best = line.id;
    }
  }
  return best;
}
