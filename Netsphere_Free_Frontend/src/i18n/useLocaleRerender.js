import { useEffect, useState } from 'react';
import { getLocale, getLocaleChangeEventName } from './index';

export const useLocaleRerender = () => {
  const [locale, setLocale] = useState(getLocale());

  useEffect(() => {
    const eventName = getLocaleChangeEventName();
    const handleLocaleChanged = (event) => {
      const next = event?.detail?.locale || getLocale();
      setLocale(next);
    };
    window.addEventListener(eventName, handleLocaleChanged);
    return () => window.removeEventListener(eventName, handleLocaleChanged);
  }, []);

  return locale;
};

