import { t } from '../i18n';
import { el } from './dom';

/** デバッグ用の fps 表示（P-3）。showFps の ON/OFF で表示を切り替える */
export type FpsIndicator = {
  update(fps: number): void;
  setVisible(visible: boolean): void;
};

export function createFpsIndicator(root: HTMLElement): FpsIndicator {
  const node = el('div', 'fps-indicator');
  node.hidden = true;
  root.append(node);
  let last = '';
  return {
    update(fps): void {
      // 表記は言語依存の整形を避け、文言側で組み立てる（architecture.md §12）
      const text = `${fps.toFixed(1)} ${t('fpsLabel')}`;
      if (text !== last) {
        last = text;
        node.textContent = text;
      }
    },
    setVisible(visible): void {
      node.hidden = !visible;
    },
  };
}
