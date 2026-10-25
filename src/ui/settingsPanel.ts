import type { AppConfig } from '../config';
import { t } from '../i18n';
import { el } from './dom';

/**
 * パラメータ調整 UI（requirements.md §7.2、F-5 / F-6）。
 * 変更は cfg への即時反映で、描画ループが次フレームから反映する。
 */
export type SettingsPanel = {
  toggle(): void;
};

export function createSettingsPanel(root: HTMLElement, cfg: AppConfig): SettingsPanel {
  const toggleButton = el('button', 'settings-toggle', t('settingsToggle'));
  const panel = el('div', 'settings-panel');
  panel.hidden = true;
  toggleButton.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
  });

  // 列数（F-5）
  addSlider(panel, t('settingColumns'), cfg.columns, 8, 160, 1, (v) => {
    cfg.columns = Math.round(v);
  }, (v) => String(Math.round(v)));

  // コントラスト
  addSlider(panel, t('settingContrast'), cfg.contrast, 0.5, 3, 0.05, (v) => {
    cfg.contrast = v;
  }, (v) => v.toFixed(2));

  // エッジのしきい値
  addSlider(panel, t('settingEdgeThreshold'), cfg.edgeThreshold, 0, 1, 0.01, (v) => {
    cfg.edgeThreshold = v;
  }, (v) => v.toFixed(2));

  // エッジの強さ（置換のしやすさ）
  addSlider(panel, t('settingEdgePriority'), cfg.edgePriority, 0, 1, 0.01, (v) => {
    cfg.edgePriority = v;
  }, (v) => v.toFixed(2));

  // 白黒反転
  addCheckbox(panel, t('settingInvert'), cfg.invert, (v) => {
    cfg.invert = v;
  });

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
  };
}

type SliderFormat = (value: number) => string;

function addSlider(
  parent: HTMLElement,
  label: string,
  initialValue: number,
  min: number,
  max: number,
  step: number,
  onChange: (value: number) => void,
  format: SliderFormat,
): void {
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
}

function addCheckbox(
  parent: HTMLElement,
  label: string,
  initialValue: boolean,
  onChange: (value: boolean) => void,
): void {
  const row = el('div', 'settings-row');
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = initialValue;
  input.addEventListener('change', () => onChange(input.checked));
  row.append(el('label', undefined, label), input);
  parent.append(row);
}
