/**
 * cmatrix 風背景アニメーションの状態管理。
 * グリッドの各列で英数記号が上から下へ落下し、先頭から末尾に向かって
 * opacity が減衰する軌跡を計算する。
 */

export const CMATRIX_CHARS =
  '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#$%&*+=<>?!:;/-_';

/** 軌跡の先頭と末尾の opacity（エッジの 1.0 より十分低くして視認性を保つ） */
const HEAD_OPACITY = 0.45;
const TAIL_OPACITY = 0.05;

interface ColumnStream {
  headY: number;
  speed: number; // cells per second
  tailLen: number;
}

export class CmatrixRain {
  private cols = 0;
  private rows = 0;
  private streams: ColumnStream[] = [];
  private lastTimeMs = 0;

  /** 各セルの CMATRIX_CHARS 内インデックス（長さ cols * rows） */
  charIds = new Uint16Array(0);
  /** 各セルの opacity（0..255。0 は非表示） */
  opacities = new Uint8Array(0);

  /**
   * 現在の時刻とグリッドサイズに合わせて雨粒の位置と各セルの opacity を更新する。
   */
  update(cols: number, rows: number, nowMs: number = performance.now()): void {
    if (cols <= 0 || rows <= 0) return;

    if (cols !== this.cols || rows !== this.rows) {
      this.resize(cols, rows);
      this.lastTimeMs = nowMs;
    }

    const dtSec = Math.min(0.1, Math.max(0, (nowMs - this.lastTimeMs) / 1000));
    this.lastTimeMs = nowMs;

    const charCount = CMATRIX_CHARS.length;
    this.opacities.fill(0);

    for (let x = 0; x < cols; x++) {
      const s = this.streams[x];
      s.headY += s.speed * dtSec;

      if (s.headY - s.tailLen > rows) {
        this.resetStream(s, rows, false);
      }

      const headCell = Math.floor(s.headY);
      // 先頭セルの文字は毎フレーム変化させ、cmatrix らしいちらつきを出す
      if (headCell >= 0 && headCell < rows) {
        this.charIds[headCell * cols + x] = Math.floor(Math.random() * charCount);
      }

      const startY = Math.max(0, Math.floor(s.headY - s.tailLen));
      const endY = Math.min(rows - 1, headCell);
      for (let y = startY; y <= endY; y++) {
        const dist = s.headY - y;
        if (dist < 0 || dist > s.tailLen) continue;
        const t = dist / s.tailLen;
        const alpha = HEAD_OPACITY - t * (HEAD_OPACITY - TAIL_OPACITY);
        const idx = y * cols + x;
        this.opacities[idx] = Math.round(alpha * 255);
        // 軌跡内の文字もごくまれに変化させる
        if (Math.random() < 0.015) {
          this.charIds[idx] = Math.floor(Math.random() * charCount);
        }
      }
    }
  }

  private resize(cols: number, rows: number): void {
    this.cols = cols;
    this.rows = rows;
    const total = cols * rows;
    this.charIds = new Uint16Array(total);
    this.opacities = new Uint8Array(total);
    const charCount = CMATRIX_CHARS.length;
    for (let i = 0; i < total; i++) {
      this.charIds[i] = Math.floor(Math.random() * charCount);
    }

    this.streams = new Array<ColumnStream>(cols);
    for (let x = 0; x < cols; x++) {
      const s: ColumnStream = { headY: 0, speed: 10, tailLen: 10 };
      this.resetStream(s, rows, true);
      this.streams[x] = s;
    }
  }

  private resetStream(s: ColumnStream, rows: number, initial: boolean): void {
    s.speed = 6 + Math.random() * 10;
    s.tailLen = Math.max(5, Math.round(rows * (0.25 + Math.random() * 0.35)));
    s.headY = initial ? -Math.random() * rows : -Math.random() * (rows * 0.4);
  }
}
