import React, { createContext, useState, useContext, useCallback, useEffect, useRef } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

// 1. Context 생성
const ToastContext = createContext(null);

// 2. Toast Provider
export const ToastProvider = ({ children }) => {
    const [toasts, setToasts] = useState([]);

    const addToast = useCallback((message, type = 'info', duration = 4000) => {
        const id = Date.now() + Math.random();
        const newToast = { id, message, type, duration, createdAt: Date.now() };

        setToasts(prev => [...prev, newToast]);

        // 자동 제거
        if (duration > 0) {
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== id));
            }, duration);
        }

        return id;
    }, []);

    const removeToast = useCallback((id) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    // 편의 함수들
    const toast = {
        success: (msg, duration) => addToast(msg, 'success', duration),
        error: (msg, duration) => addToast(msg, 'error', duration),
        warning: (msg, duration) => addToast(msg, 'warning', duration),
        info: (msg, duration) => addToast(msg, 'info', duration),
    };

    return (
        <ToastContext.Provider value={{ toast, removeToast }}>
            {children}
            <ToastContainer toasts={toasts} onRemove={removeToast} />
        </ToastContext.Provider>
    );
};

// 3. Toast Container (화면 우상단에 표시)
const ToastContainer = ({ toasts, onRemove }) => {
    return (
        <div data-testid="toast-container" className="fixed top-4 right-4 z-[9999] flex flex-col gap-3 pointer-events-none">
            {toasts.map((t) => (
                <ToastItem key={t.id} toast={t} onRemove={onRemove} />
            ))}
        </div>
    );
};

// 4. 개별 Toast 아이템 — Dark/Light 대응 + Progress Bar
const ToastItem = ({ toast, onRemove }) => {
    const [progress, setProgress] = useState(100);
    const intervalRef = useRef(null);

    useEffect(() => {
        if (!toast.duration || toast.duration <= 0) return;
        const step = 50; // ms
        const decrement = (step / toast.duration) * 100;
        intervalRef.current = setInterval(() => {
            setProgress(prev => {
                const next = prev - decrement;
                if (next <= 0) {
                    clearInterval(intervalRef.current);
                    return 0;
                }
                return next;
            });
        }, step);
        return () => clearInterval(intervalRef.current);
    }, [toast.duration]);

    const config = {
        success: {
            icon: CheckCircle,
            darkBg: 'bg-emerald-500/10 border-emerald-500/30',
            lightBg: 'bg-emerald-50 border-emerald-300',
            iconColor: 'text-emerald-500',
            darkText: 'text-emerald-300',
            lightText: 'text-emerald-700',
            glow: 'shadow-[0_0_20px_rgba(16,185,129,0.15)]',
            barColor: 'bg-emerald-500',
        },
        error: {
            icon: XCircle,
            darkBg: 'bg-red-500/10 border-red-500/30',
            lightBg: 'bg-red-50 border-red-300',
            iconColor: 'text-red-500',
            darkText: 'text-red-300',
            lightText: 'text-red-700',
            glow: 'shadow-[0_0_20px_rgba(239,68,68,0.15)]',
            barColor: 'bg-red-500',
        },
        warning: {
            icon: AlertTriangle,
            darkBg: 'bg-amber-500/10 border-amber-500/30',
            lightBg: 'bg-amber-50 border-amber-300',
            iconColor: 'text-amber-500',
            darkText: 'text-amber-300',
            lightText: 'text-amber-700',
            glow: 'shadow-[0_0_20px_rgba(245,158,11,0.15)]',
            barColor: 'bg-amber-500',
        },
        info: {
            icon: Info,
            darkBg: 'bg-blue-500/10 border-blue-500/30',
            lightBg: 'bg-blue-50 border-blue-300',
            iconColor: 'text-blue-500',
            darkText: 'text-blue-300',
            lightText: 'text-blue-700',
            glow: 'shadow-[0_0_20px_rgba(59,130,246,0.15)]',
            barColor: 'bg-blue-500',
        }
    };

    const c = config[toast.type] || config.info;
    const Icon = c.icon;

    return (
        <div
            data-testid={`toast-${toast.type}`}
            className={`
                pointer-events-auto flex items-center gap-3 px-4 py-3 relative overflow-hidden
                dark:bg-[#1b1d1f]/95 ${c.lightBg}
                dark:${c.darkBg}
                backdrop-blur-xl border rounded-xl
                ${c.glow}
                animate-slide-in-right min-w-[300px] max-w-[420px]
                transition-all duration-300
            `}
        >
            <Icon size={20} className={`${c.iconColor} shrink-0`} />
            <span className={`flex-1 text-sm font-medium dark:${c.darkText} ${c.lightText}`}>
                {toast.message}
            </span>
            <button
                onClick={() => onRemove(toast.id)}
                className="p-1 hover:bg-black/10 dark:hover:bg-white/10 rounded-lg transition-colors text-gray-400 hover:text-gray-700 dark:hover:text-white shrink-0"
            >
                <X size={14} />
            </button>

            {/* Progress Bar */}
            {toast.duration > 0 && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-black/5 dark:bg-white/5">
                    <div
                        className={`h-full ${c.barColor} opacity-60 transition-none`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            )}
        </div>
    );
};

// 5. Custom Hook
export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
};

export default ToastContext;
