/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        // CalmSekai brand palette — dark, atmospheric
        sekai: {
          bg:       '#0d0f14',
          surface:  '#151820',
          card:     '#1c2030',
          border:   '#252a3a',
          muted:    '#3a4055',
          text:     '#c8cdd8',
          subtle:   '#6b7280',
          accent:   '#7c9cbf',   // soft blue — calm, ethereal
          glow:     '#a8c4e0',
          success:  '#5a9e7c',
          warning:  '#c4965a',
          error:    '#9e5a5a',
        },
      },
      fontFamily: {
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':    'fadeIn 0.4s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
