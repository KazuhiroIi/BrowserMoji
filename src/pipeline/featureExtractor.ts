import type { AppConfig } from '../config';
import type { CellFeature, FeatureExtractor, FrameSource, GridSpec } from './types';

/**
 * 基準実装（N-4）: CPU での特徴量計算。
 * セルごとの平均輝度 + Sobel 勾配（強さ・向き・整合性）。
 * EXP-2（D-009）の基準実装（tools/prototype/selector.py・glyphfeat.py）と同じ意味:
 * - エッジ検出用の勾配強度はセル内**最大** |Sobel|（発見 1: セル平均は細い
 *   エッジを 1/featurePx に希釈する）
 * - 向きと整合性はセル内平均勾配ベクトルから（整合性 = |平均ベクトル| / 平均 |勾配|。
 *   境界を含むセルだけが高く、境界の隣は向きが打ち消し合うため低い）
 * 最適化はしない、素直な実装を優先する（architecture.md 設計原則 3）。
 */
export class CpuFeatureExtractor implements FeatureExtractor {
  extract(_frame: FrameSource, grid: GridSpec, _cfg: AppConfig): CellFeature[] {
    const w = _frame.width;
    const h = _frame.height;
    const data = _frame.data;

    const cols = grid.cols;
    const rows = grid.rows;
    const fs = grid.featurePx;

    // 輝度 0..1（1 = 白）の平面を作る（BT.601）
    const lum = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) {
      const r = data[i * 4];
      const g = data[i * 4 + 1];
      const b = data[i * 4 + 2];
      lum[i] = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    }

    const at = (x: number, y: number): number =>
      lum[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))];

    // Sobel（端は座標をクランプして処理）+ セルごとの集約
    // maxMag: セル内最大 |Sobel|（エッジ検出用）
    // sumLum / sumMag / sumVx / sumVy: 平均輝度、平均 |Sobel|、
    // 平均勾配ベクトル（整合性・向き用）
    const maxMag = new Float32Array(cols * rows);
    const sumLum = new Float32Array(cols * rows);
    const sumMag = new Float32Array(cols * rows);
    const sumVx = new Float32Array(cols * rows);
    const sumVy = new Float32Array(cols * rows);
    const blockArea = fs * fs;

    for (let y = 0; y < h; y++) {
      const cy = Math.min(rows - 1, Math.floor(y / fs));
      const rowBase = cy * cols;
      for (let x = 0; x < w; x++) {
        const cx = Math.min(cols - 1, Math.floor(x / fs));
        const i = rowBase + cx;
        const gx =
          at(x + 1, y - 1) + 2 * at(x + 1, y) + at(x + 1, y + 1) -
          (at(x - 1, y - 1) + 2 * at(x - 1, y) + at(x - 1, y + 1));
        const gy =
          at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1) -
          (at(x - 1, y - 1) + 2 * at(x, y - 1) + at(x + 1, y - 1));
        // 0..1 の輝度で最大 |gx| = 4 なので 4 で正規化する
        const mag = Math.hypot(gx, gy) / 4;
        sumLum[i] += lum[y * w + x];
        if (mag > maxMag[i]) maxMag[i] = mag;
        sumMag[i] += mag;
        sumVx[i] += gx;
        sumVy[i] += gy;
      }
    }

    const features: CellFeature[] = new Array(cols * rows);
    for (let cy = 0; cy < rows; cy++) {
      for (let cx = 0; cx < cols; cx++) {
        const i = cy * cols + cx;
        // 平均勾配ベクトル（0..1 輝度で最大 |gx| = 4 なので 4 で正規化。blockArea で平均）
        const vx = sumVx[i] / (blockArea * 4);
        const vy = sumVy[i] / (blockArea * 4);
        const meanMag = sumMag[i] / blockArea;
        const vecLen = Math.hypot(vx, vy);
        features[i] = {
          luminance: sumLum[i] / blockArea,
          gradMagnitude: maxMag[i],
          gradAngle: Math.atan2(vy, vx),
          gradCoherence: Math.min(1, vecLen / (meanMag + 1e-6)),
        };
      }
    }
    return features;
  }
}
