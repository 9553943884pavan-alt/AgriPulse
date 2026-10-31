/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Theme Colors requested:
        forest: {
          DEFAULT: '#073B2B',       // Sidebar, navigation and primary buttons
          dark: '#04241a',
          light: '#0c523c',
        },
        'fresh-leaf': {
          DEFAULT: '#16834A',       // Active states and accents
          dark: '#126c3d',
          light: '#22a05d',
        },
        'sage-mist': {
          DEFAULT: '#D9EBCB',       // Secondary backgrounds
          light: '#edf6e6',
          dark: '#bcd8a6',
        },
        'warm-cream': {
          DEFAULT: '#F7F8EE',       // Chat background and cards
          light: '#fbfcf5',
          dark: '#eef0dc',
        },
        'sunrise-gold': {
          DEFAULT: '#F3C66B',       // Small highlights and weather indicators
          light: '#f9de9e',
          dark: '#dfad45',
        },

        // Core Brand Aliases
        primary: {
          DEFAULT: '#073B2B',       // Forest Green
          soft: '#D9EBCB',          // Sage Mist
          dark: '#04241a',
          light: '#16834A',         // Fresh Leaf
          mid: '#16834A',
        },
        accent: {
          DEFAULT: '#F3C66B',       // Sunrise Gold
          gold: '#F3C66B',
          leaf: '#16834A',
        },
        drought: '#EF6C00',
        rain: '#1565C0',
        danger: '#C62828',

        // Text
        ink: '#09231A',             // Dark Forest Charcoal
        muted: '#52685E',           // Muted Forest Sage

        // Backgrounds
        surface: '#FFFFFF',
        page: '#F7F8EE',            // Warm Cream
        card: '#FFFFFF',

        // Strategy colors
        strategy: {
          traditional: '#78909C',
          lp: '#1565C0',
          qp_balanced: '#16834A',
          qp_drought: '#073B2B',
        },

        // Source badge colors
        badge: {
          live: '#16834A',
          cached: '#F3C66B',
          official: '#3B82F6',
          model: '#A855F7',
          computed: '#52685E',
          farmer: '#52685E',
          assumption: '#EF6C00',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans Devanagari', 'system-ui', 'sans-serif'],
        devanagari: ['Noto Sans Devanagari', 'sans-serif'],
      },
      fontSize: {
        base: ['16px', { lineHeight: '1.6' }],
        lg: ['18px', { lineHeight: '1.5' }],
        xl: ['20px', { lineHeight: '1.4' }],
        '2xl': ['24px', { lineHeight: '1.3' }],
        '3xl': ['28px', { lineHeight: '1.2' }],
      },
      borderRadius: {
        card: '18px',
        btn: '12px',
      },
      spacing: {},
      minHeight: {
        touch: '48px',
      },
      minWidth: {
        touch: '48px',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(7,59,43,0.06), 0 0 0 1px rgba(7,59,43,0.05)',
        'card-hover': '0 6px 18px -3px rgba(7,59,43,0.12), 0 0 0 1px rgba(7,59,43,0.08)',
        subtle: '0 2px 8px 0 rgba(7,59,43,0.04)',
      },
    },
  },
  plugins: [],
}
