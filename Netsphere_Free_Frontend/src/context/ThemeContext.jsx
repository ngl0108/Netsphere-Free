import React, { createContext, useState, useContext, useEffect } from 'react';

// 1. Context 생성
const ThemeContext = createContext(null);

// 2. Theme Provider
export const ThemeProvider = ({ children }) => {
    // localStorage에서 저장된 테마 불러오기, 없으면 'dark' 기본값
    const [theme, setTheme] = useState(() => {
        if (typeof window !== 'undefined') {
            return localStorage.getItem('theme') || 'dark';
        }
        return 'dark';
    });

    // 테마 변경 시 HTML 클래스 및 localStorage 업데이트
    useEffect(() => {
        const root = document.documentElement;

        if (theme === 'dark') {
            root.classList.add('dark');
            root.classList.remove('light');
        } else {
            root.classList.remove('dark');
            root.classList.add('light');
        }

        localStorage.setItem('theme', theme);
    }, [theme]);

    // 테마 토글 함수
    const toggleTheme = () => {
        setTheme(prev => prev === 'dark' ? 'light' : 'dark');
    };

    // 특정 테마로 설정
    const setThemeMode = (mode) => {
        if (mode === 'dark' || mode === 'light') {
            setTheme(mode);
        }
    };

    const isDark = theme === 'dark';

    return (
        <ThemeContext.Provider value={{ theme, isDark, toggleTheme, setThemeMode }}>
            {children}
        </ThemeContext.Provider>
    );
};

// 3. Custom Hook
export const useTheme = () => {
    const context = useContext(ThemeContext);
    if (!context) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
};

export default ThemeContext;
