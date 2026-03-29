import React from 'react';
import { Bell, Terminal, Download, Sun, Moon } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

const Header = () => {
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className="flex items-center justify-between border-b border-gray-200 dark:border-[#283039] px-6 py-3 bg-white/90 dark:bg-[#111418]/90 backdrop-blur-sm sticky top-0 z-10">

      {/* 왼쪽: 페이지 타이틀 */}
      <div className="flex flex-col">
        <h2 className="text-gray-900 dark:text-white text-lg font-bold leading-tight flex items-center gap-2">
          NetSphere Controller
          <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-600 dark:text-green-400 text-[10px] font-bold uppercase border border-green-500/30">
            Live
          </span>
        </h2>
        <p className="text-gray-500 dark:text-[#9dabb9] text-xs">SDN Control Plane • Multi-Vendor Support</p>
      </div>

      {/* 오른쪽: 도구 버튼들 */}
      <div className="flex items-center gap-3">
        {/* 다크모드 토글 */}
        <button
          onClick={toggleTheme}
          className="flex items-center justify-center rounded-lg w-9 h-9 bg-gray-100 dark:bg-[#283039] hover:bg-gray-200 dark:hover:bg-[#323c47] text-gray-600 dark:text-white transition-all"
          title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDark ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        {/* 알림 버튼 */}
        <button className="flex items-center justify-center rounded-lg w-9 h-9 bg-gray-100 dark:bg-[#283039] hover:bg-gray-200 dark:hover:bg-[#323c47] text-gray-600 dark:text-white transition-colors relative">
          <Bell size={18} />
          <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full border-2 border-white dark:border-[#283039]"></span>
        </button>

        {/* 터미널 버튼 */}
        <button className="flex items-center justify-center rounded-lg w-9 h-9 bg-gray-100 dark:bg-[#283039] hover:bg-gray-200 dark:hover:bg-[#323c47] text-gray-600 dark:text-white transition-colors">
          <Terminal size={18} />
        </button>

        <div className="h-8 w-[1px] bg-gray-200 dark:bg-[#283039] mx-1"></div>

        {/* 리포트 다운로드 버튼 */}
        <button className="bg-blue-600 hover:bg-blue-700 active:scale-[0.97] text-white text-sm font-bold px-4 h-9 rounded-lg flex items-center gap-2 transition-all duration-200 shadow-lg shadow-blue-600/20">
          <Download size={16} />
          <span className="hidden sm:inline">Export</span>
        </button>
      </div>
    </header>
  );
};

export default Header;