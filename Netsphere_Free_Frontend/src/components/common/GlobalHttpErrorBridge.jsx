import React, { useEffect, useRef } from 'react';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';

const getMessageForStatus = (status, serverMessage) => {
  const normalizedMessage = String(serverMessage || '').trim();
  if (normalizedMessage) return normalizedMessage;

  if (status === 401) return t('error_401_session_expired');
  if (status === 403) return t('error_403_access_denied');
  if (status === 404) return t('error_404_not_found');
  if (status >= 500) return t('error_500_server');
  if (status === 0) return t('error_network_unreachable');
  return t('error_unexpected');
};

const withRequestId = (message, requestId) => {
  const rid = String(requestId || '').trim();
  if (!rid) return message;
  return `${message} (RID: ${rid})`;
};

const GlobalHttpErrorBridge = () => {
  useLocaleRerender();
  const { toast } = useToast();
  const lastRef = useRef({ key: '', at: 0 });

  useEffect(() => {
    const handler = (event) => {
      const status = Number(event?.detail?.status || 0);
      const requestId = String(event?.detail?.requestId || '').trim();
      const baseMessage = getMessageForStatus(status, event?.detail?.message);
      const message = withRequestId(baseMessage, requestId);
      const key = `${status}:${baseMessage}`;
      const now = Date.now();

      // Prevent toast spam from polling endpoints.
      if (lastRef.current.key === key && now - lastRef.current.at < 1500) return;
      lastRef.current = { key, at: now };

      if (status === 401 || status === 403 || status === 404) {
        toast.warning(message);
        return;
      }
      toast.error(message);
    };

    window.addEventListener('netmanager:http-error', handler);
    return () => window.removeEventListener('netmanager:http-error', handler);
  }, [toast]);

  return null;
};

export default GlobalHttpErrorBridge;
