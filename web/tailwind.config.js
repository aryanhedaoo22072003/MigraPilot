/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Plus Jakarta Sans"', 'Inter', 'ui-sans-serif', 'system-ui'] },
      colors: {
        night: { 950: '#090c16', 900: '#0d1221', 800: '#151b30', 700: '#222a43' },
        azure: '#73dbff',
        lilac: '#a48bff',
      },
    },
  },
  plugins: [],
}
