import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, ChevronRight, Database, Lock, ShieldCheck, UploadCloud } from 'lucide-react';

import { AuthService, PreviewService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';

const FirstRunWizard = () => {
  const { user, refreshUser, logout } = useAuth();
  const { toast } = useToast();
  const [policy, setPolicy] = useState(null);
  const [policyLoading, setPolicyLoading] = useState(true);
  const [activeAction, setActiveAction] = useState('');
  const [passData, setPassData] = useState({ current: '', new: '', confirm: '' });
  const [eulaAccepted, setEulaAccepted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!user) {
      setPolicy(null);
      setPolicyLoading(false);
      return () => {
        cancelled = true;
      };
    }

    (async () => {
      try {
        const res = await PreviewService.getPolicy();
        if (!cancelled) {
          setPolicy(res?.data || {});
        }
      } catch (error) {
        if (!cancelled) {
          setPolicy({});
        }
      } finally {
        if (!cancelled) {
          setPolicyLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const needsEula = !user?.eula_accepted;
  const needsPassword = !!user?.must_change_password;
  const needsContributionChoice = Boolean(
    policy?.preview_enabled &&
      policy?.upload_feature_available &&
      policy?.upload_opt_in_required &&
      !policy?.upload_decision_recorded,
  );

  const steps = useMemo(() => {
    const out = [];
    if (needsEula) out.push({ key: 'eula', label: t('first_run_step_eula', 'Terms') });
    if (needsPassword) out.push({ key: 'password', label: t('first_run_step_secure', 'Secure') });
    if (needsContributionChoice) {
      out.push({ key: 'contribution', label: t('first_run_step_contribution', 'Contribution') });
    }
    return out;
  }, [needsContributionChoice, needsEula, needsPassword]);

  const activeStep = steps[0]?.key || null;
  const mustWaitForPolicy = !needsEula && !needsPassword && policyLoading;

  if (!user) {
    return null;
  }

  if (mustWaitForPolicy) {
    return (
      <div className="fixed inset-0 z-[9999] bg-[#0e1012] flex items-center justify-center p-4">
        <div className="rounded-3xl border border-gray-800 bg-[#1b1d1f] px-8 py-6 text-sm text-gray-300">
          {t('common_loading', 'Loading...')}
        </div>
      </div>
    );
  }

  if (!needsEula && !needsPassword && !needsContributionChoice) {
    return null;
  }

  const handleEulaAccept = async () => {
    setActiveAction('eula');
    try {
      await AuthService.acceptEula();
      await refreshUser();
    } catch (error) {
      toast.error(`${t('first_run_accept_eula_failed', 'Failed to accept EULA')}: ${error.message}`);
    } finally {
      setActiveAction('');
    }
  };

  const handlePasswordChange = async () => {
    if (passData.new !== passData.confirm) {
      toast.warning(t('first_run_password_mismatch', 'New passwords do not match.'));
      return;
    }
    if (passData.new.length < 8) {
      toast.warning(t('first_run_password_min_length', 'Password must be at least 8 characters.'));
      return;
    }

    setActiveAction('password');
    try {
      await AuthService.changePasswordMe(passData.current, passData.new);
      await refreshUser();
      toast.success(t('first_run_setup_complete', 'Setup Complete!'));
    } catch (error) {
      toast.error(
        `${t('first_run_change_password_failed', 'Failed to change password')}: ${error.response?.data?.detail || error.message}`,
      );
    } finally {
      setActiveAction('');
    }
  };

  const handleContributionChoice = async (enabled) => {
    setActiveAction(enabled ? 'contribution-enable' : 'contribution-skip');
    try {
      const res = await PreviewService.updateContributionConsent({
        enabled: !!enabled,
        source: 'first_run_wizard',
      });
      const nextPolicy = res?.data?.policy || {};
      const enrollment = res?.data?.enrollment || {};
      setPolicy(nextPolicy);
      toast.success(
        enabled
          ? (
              enrollment?.status === 'registered'
                ? t('first_run_contribution_enabled_registered', 'Data contribution upload is enabled and this free installation is now connected to NetSphere Cloud.')
                : t('first_run_contribution_enabled', 'Data contribution upload is enabled.')
            )
          : t('first_run_contribution_skipped', 'You can use the product without uploads and opt in later.'),
      );
    } catch (error) {
      toast.error(
        `${t('first_run_contribution_failed', 'Failed to update contribution preference')}: ${error.response?.data?.detail || error.message}`,
      );
    } finally {
      setActiveAction('');
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] bg-[#0e1012] flex items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-[#1b1d1f] border border-gray-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col max-h-[92vh]">
        <div className="p-8 border-b border-gray-800 flex flex-wrap items-center justify-between gap-4 bg-black/20">
          <div>
            <h1 className="text-2xl font-black text-white flex items-center gap-3">
              <img src="/logo_icon.png" alt="Logo" className="w-8 h-8 object-contain" />
              {t('first_run_welcome', 'Welcome to NetSphere')}
            </h1>
            <p className="text-gray-500 mt-2 text-sm font-medium">
              {t('first_run_security_setup_required', 'Initial setup required before first use')}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={logout} className="text-xs text-gray-500 hover:text-white underline mr-2">
              {t('layout_logout', 'Logout')}
            </button>
            {steps.map((step, index) => (
              <React.Fragment key={step.key}>
                {index > 0 ? <div className="w-6 h-[2px] bg-gray-800 self-center" /> : null}
                <StepIndicator
                  num={index + 1}
                  active={activeStep === step.key}
                  done={false}
                  label={step.label}
                />
              </React.Fragment>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-10 custom-scrollbar">
          {activeStep === 'eula' ? (
            <div className="space-y-6 animate-fade-in">
              <div className="flex items-center gap-3 text-amber-500 bg-amber-500/10 p-4 rounded-xl border border-amber-500/20">
                <AlertTriangle size={24} />
                <div className="text-xs font-bold">{t('first_run_read_carefully', 'PLEASE READ CAREFULLY BEFORE PROCEEDING')}</div>
              </div>

              <div className="prose prose-invert prose-sm max-w-none bg-black/30 p-6 rounded-xl border border-gray-800 h-64 overflow-y-auto text-gray-400">
                <h3>End User License Agreement (EULA)</h3>
                <p>
                  <strong>1. Disclaimer of Warranty</strong>
                  <br />
                  This software is provided "as is" without warranty of any kind. The entire risk as to the quality and
                  performance of the software is with you.
                </p>
                <p>
                  <strong>2. Limitation of Liability</strong>
                  <br />
                  In no event unless required by applicable law or agreed to in writing will the licensor be liable for
                  damages arising out of the use or inability to use the software.
                </p>
                <p>
                  <strong>3. Network Operations Warning</strong>
                  <br />
                  This free edition can discover and analyze network infrastructure. Test carefully before using it against any
                  environment you do not fully control.
                </p>
              </div>

              <label className="flex items-center gap-4 group cursor-pointer p-4 rounded-xl hover:bg-white/5 transition-colors border border-transparent hover:border-gray-700">
                <input
                  type="checkbox"
                  className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500/50"
                  checked={eulaAccepted}
                  onChange={(event) => setEulaAccepted(event.target.checked)}
                />
                <span className="text-sm text-gray-300 group-hover:text-white transition-colors">
                  {t('first_run_eula_agree', 'I have read and agree to the End User License Agreement')}
                </span>
              </label>
            </div>
          ) : null}

          {activeStep === 'password' ? (
            <div className="space-y-8 animate-fade-in max-w-md mx-auto py-4">
              <div className="text-center">
                <div className="w-16 h-16 bg-blue-500/10 text-blue-500 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Lock size={32} />
                </div>
                <h3 className="text-xl font-bold text-white">{t('first_run_secure_account', 'Secure Your Account')}</h3>
                <p className="text-sm text-gray-500 mt-2">
                  {t('first_run_default_password_warning', 'The default password is unsafe. Please set a strong password to continue.')}
                </p>
              </div>

              <div className="space-y-4">
                <Input
                  label={t('first_run_current_password', 'Current Password')}
                  type="password"
                  value={passData.current}
                  onChange={(event) => setPassData({ ...passData, current: event.target.value })}
                />
                <Input
                  label={t('first_run_new_password', 'New Password')}
                  type="password"
                  value={passData.new}
                  onChange={(event) => setPassData({ ...passData, new: event.target.value })}
                  placeholder={t('first_run_min_8_chars', 'Min 8 chars')}
                />
                <Input
                  label={t('first_run_confirm_password', 'Confirm Password')}
                  type="password"
                  value={passData.confirm}
                  onChange={(event) => setPassData({ ...passData, confirm: event.target.value })}
                />
              </div>
            </div>
          ) : null}

          {activeStep === 'contribution' ? (
            <div className="space-y-8 animate-fade-in">
              <div className="max-w-2xl mx-auto">
                <div className="w-16 h-16 bg-emerald-500/10 text-emerald-400 rounded-2xl flex items-center justify-center mb-4">
                  <UploadCloud size={32} />
                </div>
                <h3 className="text-xl font-bold text-white">{t('first_run_contribution_title', 'Optional parser improvement data sharing')}</h3>
                <p className="text-sm text-gray-400 mt-3 leading-7">
                  {t(
                    'first_run_contribution_desc',
                    'You can use auto discovery, auto topology, and connected NMS without uploading any data. If you opt in, NetSphere will allow masked raw CLI contribution uploads after you review the sanitized preview locally.',
                  )}
                </p>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 dark:border-emerald-900 dark:bg-emerald-950/10 p-5">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900 dark:text-emerald-300">
                    <ShieldCheck size={16} />
                    {t('first_run_contribution_included_title', 'What happens if you opt in')}
                  </div>
                  <ul className="mt-3 space-y-2 text-sm text-emerald-800 dark:text-emerald-200">
                    <li>- {t('first_run_contribution_included_item_1', 'Only allowlisted read-only commands can be prepared for upload.')}</li>
                    <li>- {t('first_run_contribution_included_item_2', 'NetSphere masks IPs, hostnames, serials, MACs, emails, and secret-bearing lines locally first.')}</li>
                    <li>- {t('first_run_contribution_included_item_3', 'You review the sanitized preview before every upload.')}</li>
                    <li>- {t('first_run_contribution_included_item_4', 'You can disable uploads later from the Data Contribution page.')}</li>
                  </ul>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-950/20 p-5">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-200">
                    <Database size={16} />
                    {t('first_run_contribution_not_required_title', 'What still works without it')}
                  </div>
                  <ul className="mt-3 space-y-2 text-sm text-slate-700 dark:text-slate-300">
                    <li>- {t('first_run_contribution_not_required_item_1', 'Auto discovery and device onboarding')}</li>
                    <li>- {t('first_run_contribution_not_required_item_2', 'Auto topology, Path Trace, and diagnosis')}</li>
                    <li>- {t('first_run_contribution_not_required_item_3', 'Inventory, observability, alerts, and connected NMS views')}</li>
                    <li>- {t('first_run_contribution_not_required_item_4', 'Local sanitize preview for your own review')}</li>
                  </ul>
                </div>
              </div>

              <div className="rounded-2xl border border-gray-200 dark:border-white/10 p-5 bg-black/20 max-w-2xl mx-auto">
                <div className="text-sm font-semibold text-white">{t('first_run_contribution_consent_title', 'Contribution consent')}</div>
                <p className="mt-3 text-sm text-gray-400 leading-7">
                  {t(
                    'first_run_contribution_consent_copy',
                    'By enabling contribution upload, you agree that only masked raw output you explicitly review and send will be uploaded for parser improvement. This installation-level choice is recorded once and stays locked until reset or reinstall.',
                  )}
                </p>
              </div>

              <div className="rounded-2xl border border-amber-200 bg-amber-50/70 dark:border-amber-900 dark:bg-amber-950/10 p-5 max-w-2xl mx-auto">
                <div className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-300">
                  <Lock size={16} />
                  {t('first_run_contribution_lock_title', 'Installation policy lock')}
                </div>
                <p className="mt-3 text-sm text-amber-800 dark:text-amber-200 leading-7">
                  {t(
                    'first_run_contribution_lock_copy',
                    'This contribution decision is stored as an installation policy. It cannot be changed from the UI later. Reset or reinstall if the organization wants to choose again.',
                  )}
                </p>
              </div>
            </div>
          ) : null}
        </div>

        <div className="p-6 border-t border-gray-800 bg-black/20 flex justify-end gap-3 flex-wrap">
          {activeStep === 'eula' ? (
            <button
              id="btn-accept"
              disabled={!eulaAccepted || activeAction === 'eula'}
              onClick={handleEulaAccept}
              className="px-8 py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl flex items-center gap-2 shadow-lg shadow-blue-900/20 transition-all"
            >
              {activeAction === 'eula' ? t('common_loading', 'Loading...') : <>{t('first_run_accept_continue', 'Accept & Continue')} <ChevronRight size={18} /></>}
            </button>
          ) : null}

          {activeStep === 'password' ? (
            <button
              onClick={handlePasswordChange}
              disabled={activeAction === 'password' || !passData.new || !passData.confirm}
              className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl flex items-center gap-2 shadow-lg shadow-emerald-900/20 transition-all"
            >
              {activeAction === 'password' ? t('first_run_updating', 'Updating...') : <>{t('first_run_complete_setup', 'Complete Setup')} <Check size={18} /></>}
            </button>
          ) : null}

          {activeStep === 'contribution' ? (
            <>
              <button
                onClick={() => handleContributionChoice(false)}
                disabled={activeAction === 'contribution-enable' || activeAction === 'contribution-skip'}
                className="px-6 py-3 border border-gray-600 hover:border-gray-500 text-gray-200 font-bold rounded-xl transition-all disabled:opacity-50"
              >
                {activeAction === 'contribution-skip'
                  ? t('common_loading', 'Loading...')
                  : t('first_run_contribution_skip', 'Use product without uploads')}
              </button>
              <button
                onClick={() => handleContributionChoice(true)}
                disabled={activeAction === 'contribution-enable' || activeAction === 'contribution-skip'}
                className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl flex items-center gap-2 transition-all disabled:opacity-50"
              >
                {activeAction === 'contribution-enable'
                  ? t('common_loading', 'Loading...')
                  : <>{t('first_run_contribution_enable', 'Enable contribution upload')} <ChevronRight size={18} /></>}
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};

const StepIndicator = ({ num, active, done, label }) => (
  <div className={`flex items-center gap-2 ${active ? 'opacity-100' : 'opacity-40'}`}>
    <div
      className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-all ${
        active || done ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'
      }`}
    >
      {done ? <Check size={14} /> : num}
    </div>
    <span className="text-xs font-bold uppercase tracking-wider text-white hidden sm:block">{label}</span>
  </div>
);

const Input = ({ label, type, value, onChange, placeholder }) => (
  <div>
    <label className="block text-[10px] uppercase font-bold text-gray-500 mb-1.5">{label}</label>
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      className="w-full bg-black/20 border border-gray-700 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
    />
  </div>
);

export default FirstRunWizard;
