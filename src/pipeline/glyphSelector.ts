import type { AppConfig } from '../config';
import type { AtlasProvider } from './atlas';
import type { CellFeature, GlyphSelector } from './types';

/**
 * 文字選択 方式 A（architecture.md §3、D-004 の暫定実装）:
 * 輝度で濃度文字を選ぶ。勾配が edgeThreshold 以上なら、勾配の向きに
 * 最も近い線の文字へ置き換える（edgePriority で置換のしやすさを制御）。
 */
export class DensityEdgeGlyphSelector implements GlyphSelector {
  constructor(private atlasProvider: AtlasProvider) {}

  select(features: CellFeature[], cfg: AppConfig): Uint16Array {
    const atlas = this.atlasProvider.getAtlas(cfg);
    const density = atlas.densityIds;
    const ids = new Uint16Array(features.length);

    // edgePriority が大きいほど実効しきい値が下がる（= 置き替わりやすい）。
    // 既定 0.5 のとき edgeThreshold そのもの、0 で 1.5 倍、1 で 0.5 倍。
    const effectiveThreshold = cfg.edgeThreshold * (1.5 - clamp01(cfg.edgePriority));

    for (let i = 0; i < features.length; i++) {
      const f = features[i];
      const v = applyContrast(f.luminance, cfg.contrast);
      const idx = Math.min(density.length - 1, Math.max(0, Math.round(v * (density.length - 1))));
      let id = density[idx];

      if (f.gradMagnitude >= effectiveThreshold) {
        const lineId = pickLineGlyph(atlas.lineIds, f.gradAngle);
        if (lineId >= 0) id = lineId;
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

/** 勾配の向き（画面座標系・y 下向き）から、勾配と直交する「線の向き」の文字を選ぶ */
function pickLineGlyph(
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
