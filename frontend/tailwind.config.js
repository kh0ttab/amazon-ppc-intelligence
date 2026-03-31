/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Syne', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
        body: ['Outfit', 'sans-serif'],
      },
      colors: {
        void: '#04050a',
        base: '#080b14',
        surface: '#0d1117',
        accent: {
          primary: '#4f8eff',
          glow: 'rgba(79,142,255,0.15)',
          secondary: '#00d4aa',
          danger: '#ff4d6a',
          warning: '#ffb547',
          success: '#00e096',
        },
      },
    },
  },
  plugins: [],
}
