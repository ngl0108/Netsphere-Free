import React, { useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, X } from 'lucide-react';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { useLocaleRerender } from '../../i18n/useLocaleRerender';

const HaStandbyOverlay = () => {
  useLocaleRerender();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [leaderUrl, setLeaderUrl] = useState('');
  const [leaderId, setLeaderId] = useState('');

  useEffect(() => {
    const handler = (e) => {
      const detail = e?.detail || {};
      const url = String(detail.leader_url || '');
      const id = String(detail.leader_id || '');
      setLeaderUrl(url);
      setLeaderId(id);
      setOpen(true);
      toast.warning(t('ha_standby_toast'));
    };
    window.addEventListener('netmanager:ha-standby', handler);
    return () => window.removeEventListener('netmanager:ha-standby', handler);
  }, [toast]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[9998] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-[#1b1d1f] border border-gray-800 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-amber-400" size={18} />
            <div className="text-sm font-bold text-gray-100">{t('ha_standby_title')}</div>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="p-2 rounded-lg hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            aria-label={t('common_close')}
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div className="text-sm text-gray-300">{t('ha_standby_desc')}</div>
          {(leaderUrl || leaderId) && (
            <div className="text-xs text-gray-500 space-y-1">
              {leaderId ? (
                <div>
                  {t('ha_leader_id')}: <span className="text-gray-300 font-mono">{leaderId}</span>
                </div>
              ) : null}
              {leaderUrl ? (
                <div>
                  {t('ha_leader_url')}:{' '}
                  <span className="text-gray-300 font-mono break-all">{leaderUrl}</span>
                </div>
              ) : null}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-gray-800 flex items-center justify-end gap-3">
          <button
            onClick={() => setOpen(false)}
            className="px-4 py-2 bg-transparent border border-gray-700 hover:border-gray-500 text-gray-300 font-bold rounded-lg transition-all"
          >
            {t('common_close')}
          </button>
          <button
            onClick={() => {
              if (!leaderUrl) {
                toast.info(t('ha_leader_url_missing'));
                return;
              }
              window.location.href = leaderUrl;
            }}
            className={`px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-lg transition-all flex items-center gap-2 ${
              !leaderUrl ? 'opacity-60 cursor-not-allowed' : ''
            }`}
            disabled={!leaderUrl}
          >
            {t('ha_go_leader')} <ExternalLink size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default HaStandbyOverlay;

