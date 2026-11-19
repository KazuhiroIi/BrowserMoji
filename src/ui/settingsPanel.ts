import type { AppConfig, PipelineMode, RendererKind } from '../config';
import { applyModeDefaults } from '../config';
import { t } from '../i18n';
import { getDefaultFillerChars } from '../pipeline/atlas';
import { el } from './dom';

/**
 * パラメータ調整 UI（requirements.md §7.2、F-5 / F-6）。
 * 変更は cfg への即時反映で、描画ループが次フレームから反映する。
 */
export type SettingsPanel = {
  toggle(): void;
  syncMirror(mirror: boolean): void;
  setRendererDisabled(disabled: boolean): void;
};

export function createSettingsPanel(
  root: HTMLElement,
  cfg: AppConfig,
  webgl2Available: boolean,
): SettingsPanel {
  const toggleButton = el('button', 'settings-toggle', t('settingsToggle'));
  const panel = el('div', 'settings-panel');
  panel.hidden = true;
  toggleButton.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
  });

  // 描画方式（architecture.md §5、EXP-1。非対応環境では選択肢を無効化する。E-2）
  const rendererSelect = addSelect(panel, t('settingRenderer'), cfg.renderer, [
    { value: 'canvas2d', label: t('settingRendererCanvas2d') },
    { value: 'webgl2', label: t('settingRendererWebgl2'), disabled: !webgl2Available },
  ], t('settingRendererUnsupported'), (v) => {
    cfg.renderer = v as RendererKind;
  });

  // パイプラインの方式（EXP-2 / EXP-3 適用前の classic と、基準実装準拠の selectorA。
  // 切替 UI で変更し、次フレームから反映する。切替時に列数・しきい値・文字セットを
  // モードの既定値へ入れ替える）
  addSelect(panel, t('settingMode'), cfg.mode, [
    { value: 'classic', label: t('settingModeClassic') },
    { value: 'selectorA', label: t('settingModeSelectorA') },
  ], '', (v) => {
    cfg.mode = v as PipelineMode;
    applyModeDefaults(cfg);
    columnsSlider.setValue(cfg.columns);
    edgeThresholdSlider.setValue(cfg.edgeThreshold);
    fillerCharsInput.setValue(getDefaultFillerChars(cfg.charset));
  });

  // 列数（F-5）とエッジのしきい値はモード切替で既定値に入れ替わるため、
  // 切替後に表示を更新できるよう戻り値を受けておく
  const columnsSlider = addSlider(panel, t('settingColumns'), cfg.columns, 8, 160, 1, (v) => {
    cfg.columns = Math.round(v);
  }, (v) => String(Math.round(v)));
  const edgeThresholdSlider = addSlider(panel, t('settingEdgeThreshold'), cfg.edgeThreshold, 0, 1, 0.01, (v) => {
    cfg.edgeThreshold = v;
  }, (v) => v.toFixed(2));

  // コントラスト
  addSlider(panel, t('settingContrast'), cfg.contrast, 0.5, 3, 0.05, (v) => {
    cfg.contrast = v;
  }, (v) => v.toFixed(2));

  // エッジの強さ（置換のしやすさ）
  addSlider(panel, t('settingEdgePriority'), cfg.edgePriority, 0, 1, 0.01, (v) => {
    cfg.edgePriority = v;
  }, (v) => v.toFixed(2));

  // 白黒反転
  addCheckbox(panel, t('settingInvert'), cfg.invert, (v) => {
    cfg.invert = v;
  });

  // 左右反転（前面カメラ時は既定で true）
  const mirrorCheckbox = addCheckbox(panel, t('settingMirror'), cfg.mirror, (v) => {
    cfg.mirror = v;
  });

  // エッジのみ描画（フィラーの濃度文字を描画せず空白にする）
  addCheckbox(panel, t('settingEdgeOnly'), cfg.edgeOnly, (v) => {
    cfg.edgeOnly = v;
    cmatrixBgCheckbox.setDisabled(!v);
  });

  // cmatrix風背景（エッジのみ描画が ON のときだけ有効）
  const cmatrixBgCheckbox = addCheckbox(panel, t('settingCmatrixBg'), cfg.cmatrixBg, (v) => {
    cfg.cmatrixBg = v;
  });
  cmatrixBgCheckbox.setDisabled(!cfg.edgeOnly);

  // フィラー文字（リアルタイム編集用 textarea + 既定に戻すボタン）
  const fillerCharsInput = addFillerCharsEditor(
    panel,
    t('settingFillerChars'),
    t('settingFillerCharsReset'),
    cfg.fillerChars ?? getDefaultFillerChars(cfg.charset),
    (value) => {
      cfg.fillerChars = value;
    },
    () => {
      cfg.fillerChars = null;
      return getDefaultFillerChars(cfg.charset);
    },
  );

  // fps 表示（P-3）
  addCheckbox(panel, t('settingShowFps'), cfg.showFps, (v) => {
    cfg.showFps = v;
  });

  const wrap = el('div', 'settings');
  wrap.append(toggleButton, panel);
  root.append(wrap);

  return {
    toggle(): void {
      panel.hidden = !panel.hidden;
    },
    syncMirror(mirror: boolean): void {
      mirrorCheckbox.setValue(mirror);
    },
    setRendererDisabled(disabled: boolean): void {
      rendererSelect.disabled = disabled;
    },
  };
}

type SliderFormat = (value: number) => string;

type SelectOption = {
  value: string;
  label: string;
  /** 選択肢自体が使えない環境では disabled にする（E-2） */
  disabled?: boolean;
};

function addSelect(
  parent: HTMLElement,
  label: string,
  initialValue: string,
  options: SelectOption[],
  disabledNote: string,
  onChange: (value: string) => void,
): HTMLSelectElement {
  const row = el('div', 'settings-row');
  const input = document.createElement('select');
  for (const option of options) {
    const opt = document.createElement('option');
    opt.value = option.value;
    opt.textContent = option.disabled ? `${option.label}（${disabledNote}）` : option.label;
    opt.disabled = option.disabled === true;
    input.append(opt);
  }
  input.value = initialValue;
  if (options.find((o) => o.value === initialValue)?.disabled) {
    // 既定値が無効化されている場合も選択肢を実態に合わせる
    input.value = options.find((o) => !o.disabled)?.value ?? '';
    onChange(input.value);
  }
  input.addEventListener('change', () => onChange(input.value));
  row.append(el('label', undefined, label), input);
  parent.append(row);
  return input;
}

function addSlider(
  parent: HTMLElement,
  label: string,
  initialValue: number,
  min: number,
  max: number,
  step: number,
  onChange: (value: number) => void,
  format: SliderFormat,
): SliderHandle {
  const row = el('div', 'settings-row');
  const input = document.createElement('input');
  input.type = 'range';
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(initialValue);
  const value = el('span', 'settings-value', format(initialValue));
  input.addEventListener('input', () => {
    const v = Number(input.value);
    value.textContent = format(v);
    onChange(v);
  });
  row.append(el('label', undefined, label), input, value);
  parent.append(row);
  return {
    /** プログラム側で値を変えたときに表示へ反映する（モード切替時の既定値入れ替え用） */
    setValue(v: number): void {
      input.value = String(v);
      value.textContent = format(v);
    },
  };
}

type SliderHandle = {
  setValue(value: number): void;
};

function addCheckbox(
  parent: HTMLElement,
  label: string,
  initialValue: boolean,
  onChange: (value: boolean) => void,
): { setValue(v: boolean): void; setDisabled(disabled: boolean): void } {
  const row = el('div', 'settings-row');
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = initialValue;
  input.addEventListener('change', () => onChange(input.checked));
  row.append(el('label', undefined, label), input);
  parent.append(row);
  return {
    setValue(v: boolean): void {
      input.checked = v;
    },
    setDisabled(disabled: boolean): void {
      input.disabled = disabled;
      row.style.opacity = disabled ? '0.5' : '';
    },
  };
}

function addFillerCharsEditor(
  parent: HTMLElement,
  label: string,
  resetLabel: string,
  initialValue: string,
  onChange: (value: string) => void,
  onReset: () => string,
): { setValue(value: string): void } {
  const row = el('div', 'settings-row settings-row-stack');
  const header = el('div', 'settings-row-header');
  const resetBtn = el('button', 'settings-reset-btn', resetLabel);
  resetBtn.type = 'button';
  header.append(el('label', undefined, label), resetBtn);

  const textarea = document.createElement('textarea');
  textarea.className = 'settings-textarea';
  textarea.rows = 2;
  textarea.value = initialValue;

  let timer: number | undefined;
  textarea.addEventListener('input', () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      onChange(textarea.value);
    }, 120);
  });

  resetBtn.addEventListener('click', () => {
    window.clearTimeout(timer);
    textarea.value = onReset();
  });

  row.append(header, textarea);
  parent.append(row);

  return {
    setValue(value: string): void {
      window.clearTimeout(timer);
      textarea.value = value;
    },
  };
}
