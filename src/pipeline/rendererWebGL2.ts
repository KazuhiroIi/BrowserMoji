import type { AppConfig } from '../config';
import type { AtlasProvider, FgColor, GlyphAtlas } from './atlas';
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
 *   （charset・invert の変更時に再アップロード）
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
  private glyphTexture: WebGLTexture | null = null;
  private atlasTexture: WebGLTexture | null = null;
  /** アップロード済みのアトラス（作り直し条件とセットで持つ） */
  private atlasTextureKey = '';
  private glyphTexWidth = 0;
  private glyphTexHeight = 0;
  private vpWidth = 0;
  private vpHeight = 0;
  private lost = false;
  private uniform: Record<string, WebGLUniformLocation | null> = {};

  constructor(
    private canvas: HTMLCanvasElement,
    private atlasProvider: AtlasProvider,
  ) {
    const gl = canvas.getContext('webgl2');
    if (!gl) throw new Error('WebGL2 is not available');
    this.gl = gl;
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
    for (const name of ['uGrid', 'uAtlasCells', 'uAtlasCell', 'uBg']) {
      this.uniform[name] = gl.getUniformLocation(this.program, name);
    }
    gl.useProgram(this.program);
  }

  render(glyphIds: Uint16Array, grid: GridSpec, cfg: AppConfig, _color?: Uint8Array): void {
    const gl = this.gl;
    if (this.lost || gl.isContextLost()) return;
    const atlas = this.atlasProvider.getAtlas(cfg);
    this.ensureAtlasTexture(atlas, cfg);
    this.ensureGlyphTexture(glyphIds, grid.cols, grid.rows);

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
    // 背景: 白背景＋黒文字、invert で反転（T-6）。文字色はアトラス側に含まれる
    const bg = cfg.invert ? [0, 0, 0] : [1, 1, 1];
    gl.uniform4f(this.uniform.uGrid, grid.cols, grid.rows, grid.cellWidth, grid.cellHeight);
    gl.uniform2f(this.uniform.uAtlasCells, atlas.glyphs.length, 1);
    gl.uniform2f(this.uniform.uAtlasCell, atlas.cellWidth, atlas.cellHeight);
    gl.uniform3f(this.uniform.uBg, bg[0], bg[1], bg[2]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  /** context lost を検知したか（app.ts が Canvas 2D へフォールバックする判定に使う） */
  isContextLost(): boolean {
    return this.lost || this.gl.isContextLost();
  }

  private buildProgram(): WebGLProgram {
    const gl = this.gl;
    const vs = `#version 300 es
layout(location = 0) in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;
    const fs = `#version 300 es
precision highp float;
uniform usampler2D uGlyphs;
uniform sampler2D uAtlas;
// (cols, rows, cellWidth, cellHeight)
uniform vec4 uGrid;
// (グリフ数, 1) と (アトラス 1 セル幅 px, 高さ px)
uniform vec2 uAtlasCells;
uniform vec2 uAtlasCell;
uniform vec3 uBg;
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
  // 半テクセル inset 付き LINEAR で隣接文字のにじみを防ぐ
  float insetX = 0.5 / uAtlasCell.x;
  float insetY = 0.5 / uAtlasCell.y;
  float au = (float(id) + clamp(fu, insetX, 1.0 - insetX)) / uAtlasCells.x;
  float av = clamp(1.0 - fv, insetY, 1.0 - insetY);
  vec4 tex = texture(uAtlas, vec2(au, av));
  outColor = vec4(mix(uBg, tex.rgb, tex.a), 1.0);
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
  }

  /** アトラス canvas をテクスチャとしてアップロードする（charset・invert 変更時に再アップロード） */
  private ensureAtlasTexture(atlas: GlyphAtlas, cfg: AppConfig): void {
    const fg: FgColor = cfg.invert ? 'white' : 'black';
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
}

/** WebGL2 が使える環境かの事前判定（切替 UI の選択肢の無効化に使う。E-2） */
export function isWebGL2Available(): boolean {
  const canvas = document.createElement('canvas');
  return canvas.getContext('webgl2') !== null;
}
