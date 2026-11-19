import { t } from '../i18n';
import { el } from './dom';

export interface CaptureBarOptions {
  onCopy: () => Promise<boolean>;
  onScreenshot: () => void;
  onToggleRecord: () => void;
  recordSupported: boolean;
}

export interface CaptureBar {
  setRecording(recording: boolean): void;
  remove(): void;
}

/**
 * 画面下部中央に配置する 3 つのキャプチャボタン（コピー / 撮影 / 録画）。
 */
export function createCaptureBar(root: HTMLElement, options: CaptureBarOptions): CaptureBar {
  const bar = el('div', 'capture-bar');

  const copyBtn = createActionButton('📋', t('captureCopy'));
  let copyTimer: number | null = null;
  copyBtn.button.addEventListener('click', () => {
    void (async () => {
      const ok = await options.onCopy();
      if (copyTimer !== null) window.clearTimeout(copyTimer);
      copyBtn.setLabel(ok ? '✅' : '⚠️', t(ok ? 'captureCopied' : 'captureCopyFailed'));
      copyTimer = window.setTimeout(() => {
        copyBtn.setLabel('📋', t('captureCopy'));
        copyTimer = null;
      }, 1500);
    })();
  });

  const shotBtn = createActionButton('📷', t('captureScreenshot'));
  shotBtn.button.addEventListener('click', () => {
    options.onScreenshot();
  });

  const recordBtn = createActionButton(
    options.recordSupported ? '⏺️' : '🚫',
    t(options.recordSupported ? 'captureRecordStart' : 'captureRecordUnsupported'),
  );
  if (!options.recordSupported) {
    recordBtn.button.disabled = true;
  } else {
    recordBtn.button.addEventListener('click', () => {
      options.onToggleRecord();
    });
  }

  bar.append(copyBtn.button, shotBtn.button, recordBtn.button);
  root.append(bar);

  return {
    setRecording(recording: boolean): void {
      if (!options.recordSupported) return;
      recordBtn.button.classList.toggle('is-recording', recording);
      recordBtn.setLabel(
        recording ? '⏹️' : '⏺️',
        t(recording ? 'captureRecordStop' : 'captureRecordStart'),
      );
    },
    remove(): void {
      if (copyTimer !== null) window.clearTimeout(copyTimer);
      bar.remove();
    },
  };
}

function createActionButton(icon: string, label: string) {
  const button = el('button', 'capture-btn');
  button.type = 'button';
  const iconSpan = el('span', 'capture-btn-icon', icon);
  iconSpan.setAttribute('aria-hidden', 'true');
  const labelSpan = el('span', 'capture-btn-label', label);
  button.append(iconSpan, labelSpan);

  return {
    button,
    setLabel(newIcon: string, newLabel: string): void {
      iconSpan.textContent = newIcon;
      labelSpan.textContent = newLabel;
    },
  };
}
