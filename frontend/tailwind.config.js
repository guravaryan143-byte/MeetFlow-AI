/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        obsidian: '#09090B',
        surface: '#111114',
        borderSubtle: '#222228',
        accent: '#E4E4E7',
        emeraldGlow: '#10B981',
        amberWarn: '#F59E0B',
        roseAlert: '#F43F5E',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        playfair: ['Playfair Display', 'serif'],
      },
    },
  },
  plugins: [],
};
