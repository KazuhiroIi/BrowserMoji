import type { AppConfig } from '../config';
import type { AtlasProvider, FgColor, GlyphAtlas } from './atlas';
import { CMATRIX_CHARS, CmatrixRain } from './cmatrix';
import type { Renderer, GridSpec } from './types';

/**
 * 描画: WebGL2 のグリッドシェーダ方式（D-004 の EXP-1 検証用）。
 * 画面全体を覆う 1 枚のクアッドを 1 回の draw call で描き、フラグメントシェーダが
 * gl_FragCoord からセル位置を計算し、グリフ ID テクスチャを参照してアトラスから
 * 文字をサンプリングする。描画呼び出しは毎フレーム 1 回にまとまる。
 * 配色既定は白背景＋黒文字、invert で反転（T-6）。Canvas 2D 版と同等の見た目にする。
 *
 * - グリフ ID は毎フレーム 1 回の texSubImage2D で転送する（cols×rows の 1 チャンネル）
 * - アトラスは AtlasProvider の canvas をテクスチャとしてアップロードする
 *   （charset・invert の変更時に再アップロード）。アトラスは**不透明**なので
 *   シェーダは tex.rgb をそのまま出力する（D-011）
 * - アトラスは MAX_TEXTURE_SIZE に収まるよう縮めたセル幅で構成する（D-011）。
 *   かつては転送失敗を検知しておらず、不完全テクスチャ（サンプル値 = 不透明黒）の
 *   まま全画面を黒く塗る端末があった。失敗は getError() で検知して broken を立て、
 *   呼び出し側（app.ts）が Canvas 2D にフォールバックする
 * - サンプリングは半テクセル inset 付きの LINEAR で、隣接文字がにじまないようにする
 * - 生成時に WebGL2 が使えない環境では例外で通知する（切替 UI は事前判定で無効化する）
 * - context lost は検知して報告し、呼び出し側（app.ts）が Canvas 2D にフォールバックする
 */
export class WebGL2Renderer implements Renderer {
  /** 描画方式の名前（EXP-1 の計測表示用。Renderer インターフェースのシグネチャは変えない） */
  readonly renderMethod = 'webgl2';

  private gl: WebGL2RenderingContext;
  private program: WebGLProgram;
  private vao: WebGLVertexArrayObject;
  /** テクスチャ 1 辺の上限（px）。アトラス構成の制約として AtlasProvider に渡す（D-011） */
  private readonly maxTextureSize: number;
  private glyphTexture: WebGLTexture | null = null;
  private atlasTexture: WebGLTexture | null = null;
  /** アップロード済みのアトラス（作り直し条件とセットで持つ） */
  private atlasTextureKey = '';
  private glyphTexWidth = 0;
  private glyphTexHeight = 0;
  private vpWidth = 0;
  private vpHeight = 0;
  private lost = false;
  /** GL エラー（転送失敗など）を検知したら立てる。以後描画せず Canvas 2D へフォールバックする */
  private broken = false;
  /** 直近に検知した GL エラーコード（診断表示用。0 = エラー無し） */
  private lastGlError = 0;
  private uniform: Record<string, WebGLUniformLocation | null> = {};
  private cmatrix = new CmatrixRain();
  private cmatrixAtlasTexture: WebGLTexture | null = null;
  private cmatrixCharTexture: WebGLTexture | null = null;
  private cmatrixAlphaTexture: WebGLTexture | null = null;
  private cmatrixTexWidth = 0;
  private cmatrixTexHeight = 0;

  constructor(
    private canvas: HTMLCanvasElement,
    private atlasProvider: AtlasProvider,
  ) {
    const gl = canvas.getContext('webgl2');
    if (!gl) throw new Error('WebGL2 is not available');
    this.gl = gl;
    this.maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    gl.canvas.addEventListener('webglcontextlost', ((e: Event) => {
      e.preventDefault();
      this.lost = true;
    }) as EventListener);
    this.program = this.buildProgram();
    this.vao = gl.createVertexArray()!;
    gl.bindVertexArray(this.vao);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    // 画面全体を覆う 1 枚の三角形（3 頂点）
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    for (const name of ['uGrid', 'uAtlasCells', 'uAtlasCell', 'uBg', 'uCmatrixEnabled', 'uCmatrixAtlasLen']) {
      this.uniform[name] = gl.getUniformLocation(this.program, name);
    }
    gl.useProgram(this.program);
    // サンプラのユニットを固定する。既定では両サンプラともユニット 0 を見るため、
    // uAtlas が整数テクスチャ（uGlyphs）と衝突して draw が INVALID_OPERATION になる
    gl.uniform1i(gl.getUniformLocation(this.program, 'uGlyphs'), 0);
    gl.uniform1i(gl.getUniformLocation(this.program, 'uAtlas'), 1);
    gl.uniform1i(gl.getUniformLocation(this.program, 'uCmatrixAtlas'), 2);
    gl.uniform1i(gl.getUniformLocation(this.program, 'uCmatrixChars'), 3);
    gl.uniform1i(gl.getUniformLocation(this.program, 'uCmatrixAlpha'), 4);
    // 構築中のエラーフラグを消化しておく（最初の render() の getError を誤検知させない）
    gl.getError();
  }

  render(glyphIds: Uint16Array, grid: GridSpec, cfg: AppConfig, _color?: Uint8Array): void {
    const gl = this.gl;
    if (this.lost || this.broken || gl.isContextLost()) return;
    let atlas: GlyphAtlas;
    try {
      // テクスチャ幅上限に収まるアトラスを要求する（D-011）。極端に小さい上限で
      // 収められない場合は例外 → broken を立てて Canvas 2D へフォールバックさせる
      atlas = this.atlasProvider.getAtlas(cfg, this.maxTextureSize);
    } catch {
      this.broken = true;
      return;
    }
    const isCmatrix = cfg.edgeOnly && cfg.cmatrixBg;
    this.ensureAtlasTexture(atlas, cfg);
    this.ensureGlyphTexture(glyphIds, grid.cols, grid.rows);
    if (isCmatrix) {
      this.cmatrix.update(grid.cols, grid.rows);
      this.ensureCmatrixTextures(grid.cols, grid.rows);
    }
    // 転送の成否をここで確認する。失敗したテクスチャは「不完全」になり、サンプル値が
    // 不透明黒を返すため、描いてしまうと全画面が真っ黒になる（D-011）。黒で塗るよりは
    // 描かずに Canvas 2D へフォールバックするほうが安全
    const uploadError = gl.getError();
    if (uploadError !== gl.NO_ERROR) {
      this.lastGlError = uploadError;
      this.broken = true;
      return;
    }

    if (this.canvas.width !== this.vpWidth || this.canvas.height !== this.vpHeight) {
      this.vpWidth = this.canvas.width;
      this.vpHeight = this.canvas.height;
      gl.viewport(0, 0, this.vpWidth, this.vpHeight);
    }

    gl.useProgram(this.program);
    gl.bindVertexArray(this.vao);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.glyphTexture);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.atlasTexture);
    // 背景: 白背景＋黒文字、invert で反転（T-6）。cmatrix モード時は黒背景＋緑文字
    const bg = isCmatrix || cfg.invert ? [0, 0, 0] : [1, 1, 1];
    gl.uniform4f(this.uniform.uGrid, grid.cols, grid.rows, grid.cellWidth, grid.cellHeight);
    gl.uniform2f(this.uniform.uAtlasCells, atlas.glyphs.length, 1);
    gl.uniform2f(this.uniform.uAtlasCell, atlas.cellWidth, atlas.cellHeight);
    gl.uniform3f(this.uniform.uBg, bg[0], bg[1], bg[2]);
    gl.uniform1i(this.uniform.uCmatrixEnabled, isCmatrix ? 1 : 0);
    gl.uniform1f(this.uniform.uCmatrixAtlasLen, CMATRIX_CHARS.length);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    const drawError = gl.getError();
    if (drawError !== gl.NO_ERROR) {
      this.lastGlError = drawError;
      this.broken = true;
    }
  }

  /** context lost を検知したか（app.ts が Canvas 2D へフォールバックする判定に使う） */
  isContextLost(): boolean {
    return this.lost || this.gl.isContextLost();
  }

  /** GL エラー（転送・描画の失敗）を検知したか（同上。検知後は描画しない） */
  isBroken(): boolean {
    return this.broken;
  }

  /** fps オーバーレイなどに出す診断文字列（テクスチャ上限と GL エラーの有無。P-3 / D-011） */
  diagnosticText(): string {
    const parts = [`maxTex${this.maxTextureSize}`];
    if (this.lastGlError !== 0) parts.push(`glErr${this.lastGlError}`);
    if (this.broken) parts.push('broken');
    return parts.join(' ');
  }

  private buildProgram(): WebGLProgram {
    const gl = this.gl;
    const vs = `#version 300 es
layout(location = 0) in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;
    const fs = `#version 300 es
precision highp float;
// 整数サンプラには既定の精度がないため明示する（ドライバによってはコンパイルエラーになる）
precision highp usampler2D;
uniform usampler2D uGlyphs;
uniform sampler2D uAtlas;
uniform sampler2D uCmatrixAtlas;
uniform usampler2D uCmatrixChars;
uniform sampler2D uCmatrixAlpha;
// (cols, rows, cellWidth, cellHeight)
uniform vec4 uGrid;
// (グリフ数, 1) と (アトラス 1 セル幅 px, 高さ px)
uniform vec2 uAtlasCells;
uniform vec2 uAtlasCell;
uniform vec3 uBg;
uniform int uCmatrixEnabled;
uniform float uCmatrixAtlasLen;
out vec4 outColor;
void main() {
  // 画面のセル位置（GL は y 上向きなので行を反転する）
  float cx = floor(gl_FragCoord.x / uGrid.z);
  float cyBottom = floor(gl_FragCoord.y / uGrid.w);
  float cy = uGrid.y - 1.0 - cyBottom;
  if (cx < 0.0 || cy < 0.0 || cx >= uGrid.x || cy >= uGrid.y) {
    outColor = vec4(uBg, 1.0);
    return;
  }
  uint id = texelFetch(uGlyphs, ivec2(int(cx), int(cy)), 0).r;
  // セル内の相対位置（0..1）
  float fu = gl_FragCoord.x / uGrid.z - cx;
  float fv = gl_FragCoord.y / uGrid.w - cyBottom;
  if (uCmatrixEnabled == 1 && id == 0u) {
    float alpha = texelFetch(uCmatrixAlpha, ivec2(int(cx), int(cy)), 0).r;
    if (alpha > 0.0) {
      uint cid = texelFetch(uCmatrixChars, ivec2(int(cx), int(cy)), 0).r;
      float cu = (float(cid) + clamp(fu, 0.02, 0.98)) / uCmatrixAtlasLen;
      float cv = clamp(1.0 - fv, 0.02, 0.98);
      vec4 ctex = texture(uCmatrixAtlas, vec2(cu, cv));
      outColor = vec4(ctex.rgb * alpha, 1.0);
      return;
    }
  }
  // 半テクセル inset 付き LINEAR で隣接文字のにじみを防ぐ
  float insetX = 0.5 / uAtlasCell.x;
  float insetY = 0.5 / uAtlasCell.y;
  float au = (float(id) + clamp(fu, insetX, 1.0 - insetX)) / uAtlasCells.x;
  float av = clamp(1.0 - fv, insetY, 1.0 - insetY);
  // アトラスは背景色まで塗った不透明画像なので、そのまま出力する（D-011）
  vec4 tex = texture(uAtlas, vec2(au, av));
  outColor = vec4(tex.rgb, 1.0);
}`;
    const compile = (type: number, src: string): WebGLShader => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(shader) ?? 'shader compile error');
      }
      return shader;
    };
    const program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vs));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) ?? 'program link error');
    }
    return program;
  }

  /** グリフ ID の 1 チャンネル整数テクスチャ。毎フレーム 1 回の texSubImage2D で更新する */
  private ensureGlyphTexture(glyphIds: Uint16Array, cols: number, rows: number): void {
    const gl = this.gl;
    if (!this.glyphTexture) {
      this.glyphTexture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.glyphTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.glyphTexture);
    // 転送元は 2 バイト/ピクセル（Uint16Array）。行の先頭は UNPACK_ALIGNMENT の倍数
    // オフセットでなければならず、既定の 4 では奇数列（例: 33 列）で行がずれて
    // GL エラーになる。任意の列数で転送できるよう 2 バイト境界に緩め、転送後に戻す
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 2);
    if (this.glyphTexWidth !== cols || this.glyphTexHeight !== rows) {
      // 画面回転などで格子が変わったときは領域を確保し直す
      this.glyphTexWidth = cols;
      this.glyphTexHeight = rows;
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.R16UI,
        cols,
        rows,
        0,
        gl.RED_INTEGER,
        gl.UNSIGNED_SHORT,
        glyphIds,
      );
    } else {
      gl.texSubImage2D(
        gl.TEXTURE_2D,
        0,
        0,
        0,
        cols,
        rows,
        gl.RED_INTEGER,
        gl.UNSIGNED_SHORT,
        glyphIds,
      );
    }
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4);
  }

  /** アトラス canvas をテクスチャとしてアップロードする（charset・invert・cmatrix 変更時に再アップロード） */
  private ensureAtlasTexture(atlas: GlyphAtlas, cfg: AppConfig): void {
    const fg: FgColor = cfg.edgeOnly && cfg.cmatrixBg ? 'green' : cfg.invert ? 'white' : 'black';
    const key = `${atlas.charset}/${fg}`;
    if (this.atlasTexture && this.atlasTextureKey === key) return;

    const gl = this.gl;
    if (!this.atlasTexture) {
      this.atlasTexture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.atlasTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.atlasTexture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, atlas.canvasFor(fg));
    this.atlasTextureKey = key;
  }

  /** cmatrix 用の文字アトラス（初回のみ）とセルごとの文字ID・opacity テクスチャを更新する */
  private ensureCmatrixTextures(cols: number, rows: number): void {
    const gl = this.gl;

    if (!this.cmatrixAtlasTexture) {
      const cellW = 32;
      const cellH = 48;
      const canvas = document.createElement('canvas');
      canvas.width = cellW * CMATRIX_CHARS.length;
      canvas.height = cellH;
      const ctx = canvas.getContext('2d')!;
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#00ff41';
      ctx.font = `bold ${Math.floor(cellH * 0.8)}px monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      for (let i = 0; i < CMATRIX_CHARS.length; i++) {
        ctx.fillText(CMATRIX_CHARS[i], i * cellW + cellW * 0.5, cellH * 0.5);
      }

      this.cmatrixAtlasTexture = gl.createTexture();
      gl.activeTexture(gl.TEXTURE2);
      gl.bindTexture(gl.TEXTURE_2D, this.cmatrixAtlasTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvas);
    }

    const sizeChanged = this.cmatrixTexWidth !== cols || this.cmatrixTexHeight !== rows;
    if (sizeChanged) {
      this.cmatrixTexWidth = cols;
      this.cmatrixTexHeight = rows;
    }

    if (!this.cmatrixCharTexture) {
      this.cmatrixCharTexture = gl.createTexture();
      gl.activeTexture(gl.TEXTURE3);
      gl.bindTexture(gl.TEXTURE_2D, this.cmatrixCharTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    } else {
      gl.activeTexture(gl.TEXTURE3);
      gl.bindTexture(gl.TEXTURE_2D, this.cmatrixCharTexture);
    }
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 2);
    if (sizeChanged) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.R16UI, cols, rows, 0, gl.RED_INTEGER, gl.UNSIGNED_SHORT, this.cmatrix.charIds);
    } else {
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, cols, rows, gl.RED_INTEGER, gl.UNSIGNED_SHORT, this.cmatrix.charIds);
    }

    if (!this.cmatrixAlphaTexture) {
      this.cmatrixAlphaTexture = gl.createTexture();
      gl.activeTexture(gl.TEXTURE4);
      gl.bindTexture(gl.TEXTURE_2D, this.cmatrixAlphaTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    } else {
      gl.activeTexture(gl.TEXTURE4);
      gl.bindTexture(gl.TEXTURE_2D, this.cmatrixAlphaTexture);
    }
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    if (sizeChanged) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, cols, rows, 0, gl.RED, gl.UNSIGNED_BYTE, this.cmatrix.opacities);
    } else {
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, cols, rows, gl.RED, gl.UNSIGNED_BYTE, this.cmatrix.opacities);
    }
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 4);
  }
}

/** WebGL2 が使える環境かの事前判定（切替 UI の選択肢の無効化に使う。E-2） */
export function isWebGL2Available(): boolean {
  const canvas = document.createElement('canvas');
  return canvas.getContext('webgl2') !== null;
}
