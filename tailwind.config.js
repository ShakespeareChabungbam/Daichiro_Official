/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans:  ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Display', 'SF Pro Text', 'Inter', 'Helvetica Neue', 'sans-serif'],
        serif: ['Playfair Display', 'Georgia', 'serif'],
        nike:  ['Anton', 'sans-serif'],
      },
      colors: {
        customBlack: '#0a0a0a',
        customWhite: '#fafafa',
        school: {
          navy:  '#0F2D5E',
          gold:  '#C9A84C',
          light: '#F5F7FA',
          mid:   '#E8ECF0',
          text:  '#1A2B4A',
          muted: '#6B7A8D',
        },
        zinc: {
          950: '#F0F4FA',
          900: '#0C2547',
          800: '#E4EBF7',
          700: '#C8D4E8',
          600: '#8A9BB5',
          500: '#697488',
          400: '#8A99B0',
          300: '#2D3F5C',
          200: '#1A2B4A',
        },
        black: '#0C2547',
      },
      boxShadow: {
        'nike':       '8px 8px 0px 0px rgba(0,0,0,1)',
        'nike-hover': '12px 12px 0px 0px rgba(0,0,0,1)',
        'school':     '0 4px 24px rgba(15,45,94,0.10)',
        'school-lg':  '0 8px 40px rgba(15,45,94,0.18)',
      }
    }
  },
  plugins: [],
}
