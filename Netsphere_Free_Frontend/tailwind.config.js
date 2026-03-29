/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // 다크모드 강제 적용
  theme: {
    extend: {
      colors: {
        background: "#0f172a", // Deep Navy
        surface: "#1e293b",
        surfaceLight: "#334155",

        // Brand Colors (Neon)
        primary: {
          DEFAULT: "#3b82f6", // Blue
          glow: "#60a5fa",    // Light Blue
          dark: "#2563eb",
        },
        secondary: "#94a3b8", // Slate 400

        // Semantic Status (Vibrant)
        success: "#10b981",    // Emerald
        danger: "#ef4444",     // Red
        warning: "#f59e0b",    // Amber
        info: "#06b6d4",       // Cyan

        // Glassmorphism System
        glass: {
          100: "rgba(255, 255, 255, 0.05)",
          200: "rgba(255, 255, 255, 0.1)",
          300: "rgba(30, 41, 59, 0.7)", // Panel BG
          border: "rgba(255, 255, 255, 0.1)",
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['Fira Code', 'monospace'], // For logs/configs
      },
      boxShadow: {
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
        'neon': '0 0 10px rgba(59, 130, 246, 0.5)',
        'neon-success': '0 0 10px rgba(16, 185, 129, 0.5)',
        'neon-danger': '0 0 10px rgba(239, 68, 68, 0.5)',
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out forwards',
        'slide-up': 'slideUp 0.4s ease-out forwards',
        'slide-down': 'slideDown 0.35s ease-out forwards',
        'scale-in': 'scaleIn 0.2s ease-out forwards',
        'slide-in-right': 'slideInRight 0.35s cubic-bezier(0.16,1,0.3,1) forwards',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow-pulse': 'glowPulse 2.5s ease-in-out infinite',
        'float': 'floatY 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        slideInRight: {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(59,130,246,0.25)' },
          '50%': { boxShadow: '0 0 22px rgba(59,130,246,0.55)' },
        },
        floatY: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        }
      }
    },
  },
  plugins: [],
}