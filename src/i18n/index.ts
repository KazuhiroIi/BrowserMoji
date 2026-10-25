import type { MessageKey } from './keys';
import { ja } from './ja';

export type { MessageKey, MessageDict } from './keys';

const dictionaries = { ja } as const;

export type Locale = keyof typeof dictionaries;

let current: Locale = 'ja';

export function setLocale(locale: Locale): void {
  current = locale;
}

/** 辞書から文言を引く。文言は必ず辞書経由にする（N-9） */
export function t(key: MessageKey): string {
  return dictionaries[current][key];
}
