import type { AppConfig } from '../config';
import type { CellFeature, FeatureExtractor, FrameSource, GridSpec } from './types';

/**
 * 基準実装（N-4）: CPU での特徴量計算。
 * セルごとの平均輝度 + Sobel 勾配（強さ・向き）。
 * 最適化はしない、素直な実装を優先する（architecture.md 設計原則 3）。
 */
export class CpuFeatureExtractor implements FeatureExtractor {
  extract(_frame: FrameSource, grid: GridSpec, _cfg: AppConfig): CellFeature[] {
    const { width: w, height: h, data } = _frame;
    const n = grid.cols * grid.rows;

    // セルごとの平均輝度（前処理で 1px = 1 セルに縮小済みなので、画素の輝度がそのまま平均）
    const lum = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const r = data[i * 4];
      const g = data[i * 4 + 1];
      const b = data[i * 4 + 2];
      lum[i] = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    }

    const at = (x: number, y: number): number =>
      lum[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))];

    const features: CellFeature[] = new Array(n);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        // Sobel（端は座標をクランプして処理）
        const gx =
          at(x + 1, y - 1) + 2 * at(x + 1, y) + at(x + 1, y + 1) -
          (at(x - 1, y - 1) + 2 * at(x - 1, y) + at(x - 1, y + 1));
        const gy =
          at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1) -
          (at(x - 1, y - 1) + 2 * at(x, y - 1) + at(x + 1, y - 1));
        // 0..1 の輝度で最大 |gx| = 4 なので 4 で正規化する
        const gradMagnitude = Math.hypot(gx, gy) / 4;
        const gradAngle = Math.atan2(gy, gx);
        features[y * w + x] = { luminance: lum[y * w + x], gradMagnitude, gradAngle };
      }
    }
    return features;
  }
}
