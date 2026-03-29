import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, ArrowRight } from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { AuthService } from '../api/services';
import { t } from '../i18n';

const LOGIN_INVALID_CODES = new Set([
  'AUTH_CREDENTIALS_INVALID',
  'AUTH_INVALID_CREDENTIALS',
  'AUTH_USER_NOT_FOUND',
]);

const getApiErrorCode = (err) => {
  const detail = err?.response?.data?.detail;
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') return detail.code.trim();
  const envelope = err?.response?.data?.error;
  if (envelope && typeof envelope === 'object' && typeof envelope.code === 'string') return envelope.code.trim();
  return '';
};

const getErrorMessage = (err, fallback) => {
  const status = Number(err?.response?.status || 0);
  const code = getApiErrorCode(err);
  const rawMessage = typeof err?.message === 'string' ? err.message.trim() : '';
  const normalizedMessage = rawMessage.toLowerCase();
  const detail = err?.response?.data?.detail;
  const detailMessage = typeof detail?.message === 'string' ? detail.message.trim() : '';
  const normalizedDetailMessage = detailMessage.toLowerCase();
  if (status === 401 || LOGIN_INVALID_CODES.has(code)) {
    return t('login_invalid_credentials');
  }
  if (
    /status code 401/i.test(rawMessage) ||
    normalizedMessage.includes('incorrect username or password') ||
    normalizedMessage.includes('invalid credentials') ||
    normalizedDetailMessage.includes('incorrect username or password') ||
    normalizedDetailMessage.includes('invalid credentials')
  ) {
    return t('login_invalid_credentials');
  }
  if (typeof detail === 'string' && detail.trim()) {
    if (/status code 401/i.test(detail)) return t('login_invalid_credentials');
    return detail;
  }
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message;
    if (Array.isArray(detail.errors) && detail.errors.length > 0) return detail.errors.join(' ');
  }
  if (rawMessage) return rawMessage;
  return fallback;
};

const LoginPage = () => {
  const navigate = useNavigate();
  const { login, verifyOtp } = useAuth();
  const showDevAccessHint = String(import.meta.env.VITE_SHOW_DEV_LOGIN_HINT || '').trim().toLowerCase() === 'true';
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [challengeId, setChallengeId] = useState(null);
  const [step, setStep] = useState('password'); // password | otp
  const [otpFocusSignal, setOtpFocusSignal] = useState(0);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [bootstrapRequired, setBootstrapRequired] = useState(false);
  const [bootstrapForm, setBootstrapForm] = useState({
    username: 'admin',
    fullName: 'NetSphere Administrator',
    email: '',
    password: '',
    confirm: '',
  });

  const otpLength = 6;
  const otpDigits = useMemo(() => {
    const s = String(otp || '').replace(/\D/g, '').slice(0, otpLength);
    return Array.from({ length: otpLength }, (_, i) => s[i] || '');
  }, [otp, otpLength]);

  useEffect(() => {
    if (step === 'otp') setOtpFocusSignal((x) => x + 1);
  }, [step]);

  useEffect(() => {
    const reason = sessionStorage.getItem('nm_auth_redirect_reason');
    if (reason === '401') {
      setError(t('login_session_expired'));
      sessionStorage.removeItem('nm_auth_redirect_reason');
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const response = await AuthService.bootstrapStatus();
        const data = response?.data?.data || response?.data || {};
        if (!cancelled) {
          setBootstrapRequired(Boolean(data?.enabled && data?.initial_admin_required));
        }
      } catch (err) {
        if (!cancelled) {
          setBootstrapRequired(false);
        }
      } finally {
        if (!cancelled) {
          setBootstrapLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      const result = await login(username, password);

      if (result?.mfaRequired) {
        setChallengeId(result.challengeId);
        setOtp('');
        setStep('otp');
        setOtpFocusSignal((x) => x + 1);
        return;
      }

      if (result?.success) {
        navigate('/', { replace: true });
      } else {
        throw new Error(t('login_failed_generic'));
      }
    } catch (err) {
      console.error('Login Failed:', err);
      setError(getErrorMessage(err, t('login_invalid_credentials')));
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      const result = await verifyOtp(challengeId, otp);
      if (result?.success) {
        navigate('/', { replace: true });
      } else {
        throw new Error(t('login_invalid_otp'));
      }
    } catch (err) {
      console.error('OTP Verify Failed:', err);
      setError(getErrorMessage(err, t('login_invalid_otp')));
    } finally {
      setIsLoading(false);
    }
  };

  const handleInitialAdminCreate = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    if (bootstrapForm.password !== bootstrapForm.confirm) {
      setError(t('login_initial_admin_password_mismatch', 'Passwords do not match.'));
      setIsLoading(false);
      return;
    }

    try {
      await AuthService.createInitialAdmin({
        username: bootstrapForm.username,
        full_name: bootstrapForm.fullName,
        email: bootstrapForm.email || null,
        password: bootstrapForm.password,
      });

      const result = await login(bootstrapForm.username, bootstrapForm.password);
      if (result?.success) {
        navigate('/', { replace: true });
        return;
      }
      throw new Error(t('login_failed_generic'));
    } catch (err) {
      console.error('Initial admin creation failed:', err);
      setError(getErrorMessage(err, t('login_initial_admin_create_failed', 'Failed to create the initial administrator.')));
    } finally {
      setIsLoading(false);
    }
  };

  const showInitialAdminSetup = !bootstrapLoading && bootstrapRequired && step === 'password';

  return (
    <div className="min-h-[100dvh] bg-[#0e1012] flex flex-col items-center justify-center p-4">
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(600px,90vw)] h-[min(600px,90vw)] bg-blue-900/10 rounded-full blur-[100px] pointer-events-none"></div>

      <div className="mb-8 text-center z-10 animate-fade-in-down">
        <div className="flex items-center justify-center gap-4 mb-2">
          <img
            src="/logo_icon_final.png"
            alt="NetSphere"
            className="h-16 w-16 object-contain"
          />
          <h1 className="text-4xl font-bold text-white tracking-tight">
            NetSphere
          </h1>
        </div>
        <p className="text-blue-200/60 text-sm font-medium tracking-widest uppercase">
          {t('login_subtitle')}
        </p>
      </div>

      <div className="w-full max-w-sm bg-[#1b1d1f] border border-gray-800/50 rounded-2xl shadow-xl overflow-hidden relative z-10 animate-fade-in-up p-8">
        {bootstrapLoading ? (
          <div className="space-y-4 text-center py-10">
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto"></div>
            <p className="text-sm text-gray-400">{t('common_loading', 'Loading...')}</p>
          </div>
        ) : step === 'password' && showInitialAdminSetup ? (
          <form onSubmit={handleInitialAdminCreate} className="space-y-5">
            <div className="text-center">
              <h2 className="text-xl font-bold text-white">
                {t('login_initial_admin_title', 'Create Initial Administrator')}
              </h2>
              <p className="text-sm text-gray-400 mt-2 leading-6">
                {t(
                  'login_initial_admin_copy',
                  'This free installation has not been initialized yet. Create the first administrator to start discovery, topology, and connected NMS.',
                )}
              </p>
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{t('login_username')}</label>
              <div className="relative">
                <User className="absolute left-3 top-2.5 text-gray-500" size={18} />
                <input
                  type="text"
                  required
                  value={bootstrapForm.username}
                  onChange={(e) => setBootstrapForm((prev) => ({ ...prev, username: e.target.value }))}
                  autoComplete="username"
                  className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                  placeholder={t('login_initial_admin_username_placeholder', 'admin')}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                {t('login_initial_admin_full_name', 'Full Name')}
              </label>
              <input
                type="text"
                value={bootstrapForm.fullName}
                onChange={(e) => setBootstrapForm((prev) => ({ ...prev, fullName: e.target.value }))}
                autoComplete="name"
                className="w-full px-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                placeholder={t('login_initial_admin_full_name_placeholder', 'NetSphere Administrator')}
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                {t('login_initial_admin_email', 'Email (Optional)')}
              </label>
              <input
                type="email"
                value={bootstrapForm.email}
                onChange={(e) => setBootstrapForm((prev) => ({ ...prev, email: e.target.value }))}
                autoComplete="email"
                className="w-full px-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                placeholder={t('login_initial_admin_email_placeholder', 'admin@example.com')}
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{t('login_password')}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-2.5 text-gray-500" size={18} />
                <input
                  type="password"
                  required
                  value={bootstrapForm.password}
                  onChange={(e) => setBootstrapForm((prev) => ({ ...prev, password: e.target.value }))}
                  autoComplete="new-password"
                  className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                  placeholder={t('login_password_placeholder')}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
                {t('login_initial_admin_confirm_password', 'Confirm Password')}
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-2.5 text-gray-500" size={18} />
                <input
                  type="password"
                  required
                  value={bootstrapForm.confirm}
                  onChange={(e) => setBootstrapForm((prev) => ({ ...prev, confirm: e.target.value }))}
                  autoComplete="new-password"
                  className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                  placeholder={t('login_password_placeholder')}
                />
              </div>
            </div>

            {error && (
              <div data-testid="login-error-message" className="text-red-500 text-sm text-center font-medium bg-red-500/10 py-2 rounded-lg border border-red-500/20">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <>{t('login_initial_admin_submit', 'Create Administrator')} <ArrowRight size={18} /></>
              )}
            </button>
          </form>
        ) : step === 'password' ? (
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{t('login_username')}</label>
              <div className="relative">
                <User className="absolute left-3 top-2.5 text-gray-500" size={18} />
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                  placeholder={t('login_username_placeholder')}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{t('login_password')}</label>
              <div className="relative">
                <Lock className="absolute left-3 top-2.5 text-gray-500" size={18} />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                  placeholder={t('login_password_placeholder')}
                />
              </div>
            </div>

            {error && (
              <div data-testid="login-error-message" className="text-red-500 text-sm text-center font-medium bg-red-500/10 py-2 rounded-lg border border-red-500/20">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <>{t('login_title')} <ArrowRight size={18} /></>
              )}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyOtp} className="space-y-5">
            <div className="text-sm text-gray-300 font-medium">
              {t('login_otp_prompt')}
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">{t('login_otp_label')}</label>
              <div className="flex items-center gap-3">
                <Lock className="text-gray-500" size={18} />
                <OtpCodeInput
                  length={otpLength}
                  digits={otpDigits}
                  focusSignal={otpFocusSignal}
                  onChange={setOtp}
                />
              </div>
            </div>

            {error && (
              <div data-testid="login-error-message" className="text-red-500 text-sm text-center font-medium bg-red-500/10 py-2 rounded-lg border border-red-500/20">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading || String(otp || '').length !== otpLength}
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <>{t('login_verify')} <ArrowRight size={18} /></>
              )}
            </button>

            <button
              type="button"
              onClick={() => { setStep('password'); setChallengeId(null); setOtp(''); setError(''); }}
              disabled={isLoading}
              className="w-full bg-transparent border border-gray-700 hover:border-gray-500 text-gray-300 font-bold py-2.5 rounded-lg transition-all duration-200 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {t('login_back')}
            </button>
          </form>
        )}

        {showDevAccessHint && (
          <div className="mt-6 text-center">
            <p className="text-xs text-gray-500">
              {t('login_dev_access_hint', 'Development mode: use a provisioned test account.')}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

const OtpCodeInput = ({ length = 6, digits, focusSignal, onChange }) => {
  const inputsRef = useRef([]);

  useEffect(() => {
    const idx = digits.findIndex((d) => !d);
    const target = idx >= 0 ? idx : Math.max(0, digits.length - 1);
    const el = inputsRef.current[target];
    if (el && typeof el.focus === 'function') el.focus();
  }, [focusSignal, digits]);

  const setAt = (index, nextChar) => {
    const clean = String(nextChar || '').replace(/\D/g, '').slice(-1);
    const nextDigits = [...digits];
    nextDigits[index] = clean;
    onChange(nextDigits.join(''));
    if (clean && index < nextDigits.length - 1) {
      const el = inputsRef.current[index + 1];
      if (el && typeof el.focus === 'function') el.focus();
    }
  };

  const handlePaste = (e) => {
    const text = (e.clipboardData?.getData('text') || '').replace(/\D/g, '');
    if (!text) return;
    e.preventDefault();
    const nextDigits = Array.from({ length: Number(length) || 6 }, (_, i) => text[i] || '');
    onChange(nextDigits.join(''));
    const idx = nextDigits.findIndex((d) => !d);
    const target = idx >= 0 ? idx : Math.max(0, nextDigits.length - 1);
    const el = inputsRef.current[target];
    if (el && typeof el.focus === 'function') el.focus();
  };

  return (
    <div className="flex gap-2" onPaste={handlePaste}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { inputsRef.current[i] = el; }}
          value={d}
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          onChange={(e) => setAt(i, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Backspace') {
              if (digits[i]) {
                setAt(i, '');
              } else if (i > 0) {
                const prev = inputsRef.current[i - 1];
                if (prev && typeof prev.focus === 'function') prev.focus();
              }
            }
          }}
          className="w-10 h-10 text-center bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
        />
      ))}
    </div>
  );
};

export default LoginPage;
