import { t, type MessageKey } from '../i18n';
import { el } from './dom';

export type StartScreen = {
  /** カメラ起動中であることを表示する */
  setStarting(): void;
  /** F-9: 原因と対処を日本語で表示する */
  showError(messageKey: MessageKey): void;
  remove(): void;
};

/**
 * 開始画面（requirements.md §7.1）:
 * アプリの説明、プライバシー表示（F-8）、「開始」ボタン。
 * カメラ権限の要求はボタン押下後に行う。
 */
export function createStartScreen(root: HTMLElement, onStart: () => void): StartScreen {
  const screen = el('section', 'start-screen');

  const title = el('h1', 'start-title', t('appName'));
  const description = el('p', 'start-description', t('appDescription'));
  const privacy = el('p', 'start-privacy', t('privacyNotice')); // F-8
  const button = el('button', 'start-button', t('startButton'));
  const starting = el('p', 'start-starting', t('startingCamera'));
  starting.hidden = true;
  const errorBox = el('div', 'start-error');
  errorBox.hidden = true;

  button.addEventListener('click', () => {
    button.disabled = true;
    onStart();
  });

  screen.append(title, description, privacy, button, starting, errorBox);
  root.append(screen);

  return {
    setStarting(): void {
      starting.hidden = false;
      button.disabled = true;
    },
    showError(messageKey): void {
      errorBox.replaceChildren(
        el('p', 'start-error-title', t('errorTitle')),
        el('p', undefined, t(messageKey)),
      );
      errorBox.hidden = false;
      starting.hidden = true;
      button.disabled = false; // 対処のうえ再試行できるようにする
    },
    remove(): void {
      screen.remove();
    },
  };
}
