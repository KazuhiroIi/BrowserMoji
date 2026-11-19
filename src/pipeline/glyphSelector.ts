import type { AppConfig } from '../config';
import type { AtlasProvider } from './atlas';
import type { CellFeature, GlyphSelector } from './types';

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

/**
 * 文字選択 方式 A の classic 版（EXP-2 / EXP-3 適用前、076886d より前の実装）:
 * 輝度で濃度文字を選ぶ。勾配が edgeThreshold 以上なら、勾配の向きに最も近い
 * 4 方向（― ＼ ｜ ／）の線の文字へ置き換える。selectorA との違い:
 * - 濃度選択が等分量子化（selectorA は計測濃度の最近傍）
 * - エッジ判定がセル平均の勾配（featurePx = 1 のとき extractor が同じ値を返す）。
 *   整合性チェック（coherenceMin）はしない
 * - 線の選択が 4 方向の向きだけ（太さ選択のスコア式なし。D-009 の前）
 */
export class ClassicGlyphSelector implements GlyphSelector {
  constructor(private atlasProvider: AtlasProvider) {}

  select(features: CellFeature[], cfg: AppConfig): Uint16Array {
    const atlas = this.atlasProvider.getAtlas(cfg);
    const density = atlas.densityIds;
    const ids = new Uint16Array(features.length);
    const blankId = density[0];

    // edgePriority が大きいほど実効しきい値が下がる（= 置き替わりやすい）。
    // 既定 0.5 のとき edgeThreshold そのもの、0 で 1.5 倍、1 で 0.5 倍。
    const effectiveThreshold = cfg.edgeThreshold * (1.5 - clamp01(cfg.edgePriority));

    for (let i = 0; i < features.length; i++) {
      const f = features[i];
      let id: number;
      if (cfg.edgeOnly) {
        id = blankId;
      } else {
        const v = applyContrast(f.luminance, cfg.contrast);
        const effectiveV = cfg.invertLuminance ? 1 - v : v;
        const idx = Math.min(density.length - 1, Math.max(0, Math.round(effectiveV * (density.length - 1))));
        id = density[idx];
      }

      if (f.gradMagnitude >= effectiveThreshold) {
        const lineId = pickLineGlyph4(atlas.lineIds, f.gradAngle);
        if (lineId >= 0) id = lineId;
      }
      ids[i] = id;
    }
    return ids;
  }
}

/** 勾配の向き（画面座標系・y 下向き）から、勾配と直交する「線の向き」の文字を選ぶ */
function pickLineGlyph4(
  lineIds: { horizontal: number; vertical: number; slash: number; backslash: number },
  gradAngle: number,
): number {
  // 線の向きは勾配の向き + 90°。0..π に正規化する
  const a = Math.atan2(Math.sin(gradAngle + Math.PI / 2), Math.cos(gradAngle + Math.PI / 2));
  let deg = (a * 180) / Math.PI;
  if (deg < 0) deg += 180;

  // 0°=―（横線）、45°=＼、90°=｜（縦線）、135°=／（0..180 で一周）
  const candidates: Array<[number, number]> = [
    [0, lineIds.horizontal],
    [45, lineIds.backslash],
    [90, lineIds.vertical],
    [135, lineIds.slash],
  ];
  let best = -1;
  let bestDist = Infinity;
  for (const [cdeg, id] of candidates) {
    let d = Math.abs(deg - cdeg);
    d = Math.min(d, 180 - d);
    if (id >= 0 && d < bestDist) {
      bestDist = d;
      best = id;
    }
  }
  return best;
}

function applyContrast(v: number, contrast: number): number {
  return Math.min(1, Math.max(0, (v - 0.5) * contrast + 0.5));
}


