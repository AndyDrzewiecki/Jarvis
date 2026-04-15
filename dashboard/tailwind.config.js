/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg:       '#0a0e1a',
          surface:  '#111827',
          border:   '#1f2937',
          accent:   '#3b82f6',
          green:    '#10b981',
          yellow:   '#f59e0b',
          red:      '#ef4444',
          dim:      '#6b7280',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
