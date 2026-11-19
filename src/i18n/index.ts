import type { MessageKey } from './keys';
import { ja } from './ja';
import { en } from './en';
import { zh } from './zh';
import { ko } from './ko';

export type { MessageKey, MessageDict } from './keys';

const dictionaries = { ja, en, zh, ko } as const;

export type Locale = keyof typeof dictionaries;

export const SUPPORTED_LOCALES: readonly Locale[] = ['ja', 'en', 'zh', 'ko'];

export const LOCALE_LABELS: Record<Locale, string> = {
  ja: '日本語',
  en: 'English',
  zh: '中文',
  ko: '한국어',
};

const STORAGE_KEY = 'browsermoji.locale';

function isSupportedLocale(value: string | null | undefined): value is Locale {
  return value === 'ja' || value === 'en' || value === 'zh' || value === 'ko';
}

function detectInitialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isSupportedLocale(saved)) {
      return saved;
    }
  } catch {
    // localStorage が使えない環境（プライベートブラウジング等）は無視する
  }

  if (typeof navigator !== 'undefined' && typeof navigator.language === 'string') {
    const primary = navigator.language.toLowerCase().split('-')[0];
    if (isSupportedLocale(primary)) {
      return primary;
    }
    return 'en';
  }

  return 'ja';
}

let current: Locale = detectInitialLocale();
if (typeof document !== 'undefined') {
  document.documentElement.lang = current;
}

export function getLocale(): Locale {
  return current;
}

export function setLocale(locale: Locale): void {
  current = locale;
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale;
  }
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // localStorage が使えない環境は無視する
  }
}

/** 辞書から文言を引く。文言は必ず辞書経由にする（N-9） */
export function t(key: MessageKey): string {
  return dictionaries[current][key];
}
