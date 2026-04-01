/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        mono:    ['DM Mono', 'monospace'],
        body:    ['Outfit', 'sans-serif'],
      },
      colors: {
        accent: {
          primary:   '#007AFF',
          glow:      'rgba(0,122,255,0.14)',
          secondary: '#5856D6',
          danger:    '#FF3B30',
          warning:   '#FF9500',
          success:   '#34C759',
        },
      },
      borderRadius: {
        '2xl': '1.25rem',
        '3xl': '1.5rem',
      },
    },
  },
  plugins: [],
}
