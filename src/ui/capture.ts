import type { GlyphInfo } from '../pipeline/atlas';

/**
 * グリフ ID 配列とグリッド寸法から、改行区切りのテキスト表現を生成する。
 */
export function glyphsToText(
  glyphIds: Uint16Array,
  cols: number,
  rows: number,
  glyphs: readonly GlyphInfo[],
): string {
  if (cols <= 0 || rows <= 0) return '';
  const lines: string[] = [];
  for (let r = 0; r < rows; r++) {
    let line = '';
    const offset = r * cols;
    for (let c = 0; c < cols; c++) {
      const id = glyphIds[offset + c];
      line += glyphs[id]?.char ?? ' ';
    }
    lines.push(line);
  }
  return lines.join('\n');
}

/**
 * タイムスタンプ付きのダウンロードファイル名を生成する。
 */
export function formatCaptureFilename(ext: string, now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `browsermoji-${date}-${time}.${ext}`;
}

/**
 * Blob をファイルとしてダウンロードさせる。
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const RECORDING_MIME_CANDIDATES = [
  'video/mp4;codecs=avc1',
  'video/mp4',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
  'video/webm',
] as const;

/**
 * MediaRecorder が対応している録画 MIME タイプを MP4 優先で選択する。
 * MediaRecorder 非対応または対応形式がない場合は null を返す。
 */
export function selectRecordingMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  if (typeof MediaRecorder.isTypeSupported !== 'function') return '';
  for (const mime of RECORDING_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return null;
}

/**
 * MIME タイプからファイル拡張子（mp4 / webm）を決定する。
 */
export function mimeTypeToExtension(mimeType: string): 'mp4' | 'webm' {
  return mimeType.includes('mp4') ? 'mp4' : 'webm';
}

/**
 * Chromium 系の MediaRecorder が出力する WebM には Duration メタデータが
 * 書き込まれないことがあるため、EBML の Info セクションに実測の録画時間を補完する。
 * 解析できない形式の場合は元の Blob をそのまま返す。
 */
export async function fixWebmDuration(blob: Blob, durationMs: number): Promise<Blob> {
  if (durationMs <= 0) return blob;
  try {
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    // Info 要素 ID: 0x15 0x49 0xA9 0x66
    const infoIdIdx = findBytes(bytes, [0x15, 0x49, 0xa9, 0x66], 0, Math.min(bytes.length, 4096));
    if (infoIdIdx < 0) return blob;

    const sizeOffset = infoIdIdx + 4;
    const sizeVint = readVint(bytes, sizeOffset);
    if (!sizeVint || sizeVint.unknown) return blob;

    const infoDataStart = sizeOffset + sizeVint.length;
    const infoDataEnd = infoDataStart + sizeVint.value;
    if (infoDataEnd > bytes.length) return blob;

    // 既存の Duration 要素 (0x44 0x89) が Info 内にあれば上書きする
    const durIdx = findBytes(bytes, [0x44, 0x89], infoDataStart, infoDataEnd);
    if (durIdx >= 0 && durIdx + 3 < infoDataEnd) {
      const durSize = readVint(bytes, durIdx + 2);
      if (durSize && (durSize.value === 4 || durSize.value === 8)) {
        const valOffset = durIdx + 2 + durSize.length;
        const view = new DataView(buffer);
        if (durSize.value === 8) {
          view.setFloat64(valOffset, durationMs, false);
        } else {
          view.setFloat32(valOffset, durationMs, false);
        }
        return new Blob([buffer], { type: blob.type });
      }
    }

    // Duration 要素が無い場合は Info の末尾に 11 バイト (0x44 0x89 0x88 + float64) を挿入する
    const newInfoSize = sizeVint.value + 11;
    const newSizeBytes = encodeVintWithLength(newInfoSize, sizeVint.length);
    if (!newSizeBytes) return blob;

    const out = new Uint8Array(bytes.length + 11);
    out.set(bytes.subarray(0, sizeOffset), 0);
    out.set(newSizeBytes, sizeOffset);
    out.set(bytes.subarray(infoDataStart, infoDataEnd), infoDataStart);

    const durEntry = new Uint8Array(11);
    durEntry[0] = 0x44;
    durEntry[1] = 0x89;
    durEntry[2] = 0x88; // size = 8 (VINT)
    new DataView(durEntry.buffer).setFloat64(3, durationMs, false);
    out.set(durEntry, infoDataEnd);
    out.set(bytes.subarray(infoDataEnd), infoDataEnd + 11);

    return new Blob([out], { type: blob.type });
  } catch {
    return blob;
  }
}

function findBytes(haystack: Uint8Array, needle: number[], start: number, end: number): number {
  const limit = Math.min(end, haystack.length) - needle.length;
  outer: for (let i = start; i <= limit; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (haystack[i + j] !== needle[j]) continue outer;
    }
    return i;
  }
  return -1;
}

function readVint(bytes: Uint8Array, offset: number): { value: number; length: number; unknown: boolean } | null {
  if (offset >= bytes.length) return null;
  const first = bytes[offset];
  let length = 1;
  let mask = 0x80;
  while (length <= 8 && (first & mask) === 0) {
    mask >>= 1;
    length++;
  }
  if (length > 8 || offset + length > bytes.length) return null;

  let value = first & ~mask;
  let allOnes = value === mask - 1;
  for (let i = 1; i < length; i++) {
    const b = bytes[offset + i];
    if (b !== 0xff) allOnes = false;
    value = value * 256 + b;
  }
  return { value, length, unknown: allOnes };
}

function encodeVintWithLength(value: number, length: number): Uint8Array | null {
  const maxVal = Math.pow(2, 7 * length) - 2;
  if (value > maxVal) return null;
  const out = new Uint8Array(length);
  let v = value;
  for (let i = length - 1; i >= 0; i--) {
    out[i] = v & 0xff;
    v = Math.floor(v / 256);
  }
  out[0] |= 1 << (8 - length);
  return out;
}
