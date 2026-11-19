import {
  getLocale,
  LOCALE_LABELS,
  setLocale,
  SUPPORTED_LOCALES,
  t,
  type Locale,
  type MessageKey,
} from '../i18n';
import { el } from './dom';

export type StartScreen = {
  /** カメラ起動中であることを表示する */
  setStarting(): void;
  /** F-9: 原因と対処を表示する */
  showError(messageKey: MessageKey): void;
  remove(): void;
};

function createGlobeSvg(): SVGSVGElement {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '20');
  svg.setAttribute('height', '20');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');

  const circle = document.createElementNS(ns, 'circle');
  circle.setAttribute('cx', '12');
  circle.setAttribute('cy', '12');
  circle.setAttribute('r', '10');

  const path1 = document.createElementNS(ns, 'path');
  path1.setAttribute('d', 'M2 12h20');

  const path2 = document.createElementNS(ns, 'path');
  path2.setAttribute(
    'd',
    'M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z',
  );

  svg.append(circle, path1, path2);
  return svg;
}

/**
 * 開始画面（requirements.md §7.1）:
 * アプリの説明、プライバシー表示（F-8）、「開始」ボタン、言語切替。
 * カメラ権限の要求はボタン押下後に行う。
 */
export function createStartScreen(root: HTMLElement, onStart: () => void): StartScreen {
  const screen = el('section', 'start-screen');

  let currentErrorKey: MessageKey | null = null;

  // 右上の言語スイッチャー（地球儀アイコン + ドロップダウン）
  const langSwitcher = el('div', 'lang-switcher');
  const langToggle = el('button', 'lang-toggle');
  langToggle.type = 'button';
  langToggle.setAttribute('aria-haspopup', 'menu');
  langToggle.setAttribute('aria-expanded', 'false');
  langToggle.append(createGlobeSvg());

  const langMenu = el('div', 'lang-menu');
  langMenu.setAttribute('role', 'menu');
  langMenu.hidden = true;

  const optionButtons = new Map<Locale, HTMLButtonElement>();

  function syncActiveLocale(): void {
    const active = getLocale();
    for (const [locale, btn] of optionButtons) {
      const isCurrent = locale === active;
      btn.classList.toggle('is-active', isCurrent);
      btn.setAttribute('aria-checked', String(isCurrent));
    }
  }

  function closeMenu(): void {
    if (langMenu.hidden) return;
    langMenu.hidden = true;
    langToggle.setAttribute('aria-expanded', 'false');
  }

  function openMenu(): void {
    langMenu.hidden = false;
    langToggle.setAttribute('aria-expanded', 'true');
  }

  const title = el('h1', 'start-title');
  const description = el('p', 'start-description');
  const privacy = el('p', 'start-privacy'); // F-8
  const button = el('button', 'start-button');
  const starting = el('p', 'start-starting');
  starting.hidden = true;
  const errorBox = el('div', 'start-error');
  errorBox.hidden = true;

  function renderTexts(): void {
    langToggle.setAttribute('aria-label', t('languageSelect'));
    langToggle.title = t('languageSelect');
    title.textContent = t('appName');
    description.textContent = t('appDescription');
    privacy.textContent = t('privacyNotice');
    button.textContent = t('startButton');
    starting.textContent = t('startingCamera');
    if (currentErrorKey !== null) {
      errorBox.replaceChildren(
        el('p', 'start-error-title', t('errorTitle')),
        el('p', undefined, t(currentErrorKey)),
      );
    }
    syncActiveLocale();
  }

  for (const locale of SUPPORTED_LOCALES) {
    const option = el('button', 'lang-option', LOCALE_LABELS[locale]);
    option.type = 'button';
    option.setAttribute('role', 'menuitemradio');
    option.addEventListener('click', () => {
      setLocale(locale);
      renderTexts();
      closeMenu();
    });
    optionButtons.set(locale, option);
    langMenu.append(option);
  }

  langToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    if (langMenu.hidden) {
      openMenu();
    } else {
      closeMenu();
    }
  });

  const onDocumentClick = (e: MouseEvent): void => {
    if (!langSwitcher.contains(e.target as Node)) {
      closeMenu();
    }
  };
  const onDocumentKeyDown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      closeMenu();
    }
  };
  document.addEventListener('click', onDocumentClick);
  document.addEventListener('keydown', onDocumentKeyDown);

  langSwitcher.append(langToggle, langMenu);

  button.addEventListener('click', () => {
    button.disabled = true;
    onStart();
  });

  renderTexts();
  screen.append(langSwitcher, title, description, privacy, button, starting, errorBox);
  root.append(screen);

  return {
    setStarting(): void {
      starting.hidden = false;
      button.disabled = true;
    },
    showError(messageKey): void {
      currentErrorKey = messageKey;
      errorBox.replaceChildren(
        el('p', 'start-error-title', t('errorTitle')),
        el('p', undefined, t(messageKey)),
      );
      errorBox.hidden = false;
      starting.hidden = true;
      button.disabled = false; // 対処のうえ再試行できるようにする
    },
    remove(): void {
      document.removeEventListener('click', onDocumentClick);
      document.removeEventListener('keydown', onDocumentKeyDown);
      screen.remove();
    },
  };
}
