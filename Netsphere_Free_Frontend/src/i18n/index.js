import { messages as baseMessages } from './messages';
import { patchMessages } from './patchMessages';
import { safeMessages } from './safeMessages';
import { finalMessages } from './finalMessages';

const LOCALE_STORAGE_KEY = 'nm_locale';
const LOCALE_CHANGE_EVENT = 'netmanager:locale-changed';
const SUPPORTED_LOCALES = ['ko', 'en'];

const isCorruptedText = (value) => {
  const text = String(value || '');
  if (!text) return false;
  if (text.includes('\uFFFD')) return true;
  if (/[\u4E00-\u9FFF]/.test(text)) return true;
  const questionMarks = (text.match(/\?/g) || []).length;
  if (questionMarks >= 2) return true;
  if (/\?[\u3131-\u314E\u314F-\u3163\uAC00-\uD7A3]/.test(text)) return true;
  return false;
};

const mergeLocaleMessages = (locale) => {
  const out = {};
  const sources = [baseMessages, patchMessages, safeMessages, finalMessages];
  for (const source of sources) {
    const group = source?.[locale];
    if (!group || typeof group !== 'object') continue;
    for (const [key, value] of Object.entries(group)) {
      if (locale === 'ko' && isCorruptedText(value)) continue;
      out[key] = value;
    }
  }
  return out;
};

const mergedMessages = {
  en: mergeLocaleMessages('en'),
  ko: mergeLocaleMessages('ko'),
};

const normalizeLocale = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  return SUPPORTED_LOCALES.includes(normalized) ? normalized : 'ko';
};

export const getLocale = () => {
  try {
    const raw = localStorage.getItem(LOCALE_STORAGE_KEY) || 'ko';
    return normalizeLocale(raw);
  } catch (e) {
    return 'ko';
  }
};

export const setLocale = (nextLocale) => {
  const locale = normalizeLocale(nextLocale);
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    window.dispatchEvent(new CustomEvent(LOCALE_CHANGE_EVENT, { detail: { locale } }));
  } catch (e) {
    // ignore storage/event failures
  }
  return locale;
};

export const getSupportedLocales = () => SUPPORTED_LOCALES.slice();
export const getLocaleChangeEventName = () => LOCALE_CHANGE_EVENT;

export const getLocaleLabel = (locale) => {
  const normalized = normalizeLocale(locale);
  if (normalized === 'en') return 'English';
  return '한국어';
};

export const t = (key, fallback = '') => {
  const locale = getLocale();
  const localized = mergedMessages?.[locale]?.[key];
  if (localized && !isCorruptedText(localized)) {
    return localized;
  }
  const english = mergedMessages?.en?.[key];
  if (english) return english;
  return fallback || key;
};

