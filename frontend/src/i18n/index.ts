import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './en.json'
import mr from './mr.json'
import hi from './hi.json'

// Read the persisted language from localStorage so the UI boots in the
// correct language after a refresh. The Zustand store writes it under
// the key 'agripulse-session' as JSON { state: { language: "mr" } }.
function getPersistedLanguage(): string {
  try {
    const raw = localStorage.getItem('agripulse-session')
    if (raw) {
      const parsed = JSON.parse(raw) as { state?: { language?: string } }
      const lang = parsed?.state?.language
      if (lang === 'mr' || lang === 'hi' || lang === 'en') return lang
    }
  } catch {
    // ignore — fall back to default
  }
  return 'en'
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    mr: { translation: mr },
    hi: { translation: hi },
  },
  lng: getPersistedLanguage(),   // ← read persisted language on boot
  fallbackLng: 'en',
  interpolation: {
    escapeValue: false,
  },
})

export default i18n
