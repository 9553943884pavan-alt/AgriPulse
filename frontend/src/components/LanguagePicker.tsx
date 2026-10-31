/** Language selector — mr / hi / en. */

import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'
import type { Language } from '@/api/types'
import { useStore } from '@/state/store'

const LANGUAGES: Language[] = ['mr', 'hi', 'en']

export function LanguagePicker({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation()
  const setLanguage = useStore((s) => s.setLanguage)
  const language = useStore((s) => s.language)

  const handleChange = (lang: Language) => {
    setLanguage(lang)
    void i18n.changeLanguage(lang)
  }

  return (
    <div className={`relative inline-flex items-center ${className}`}>
      <Globe className="w-4 h-4 text-muted absolute left-2.5 pointer-events-none" aria-hidden="true" />
      <select
        value={language}
        onChange={(e) => handleChange(e.target.value as Language)}
        aria-label="Select language"
        className="
          pl-8 pr-4 py-2 rounded-btn text-sm font-medium bg-surface border border-gray-300
          text-ink appearance-none cursor-pointer min-h-touch
          hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary
        "
      >
        {LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>
            {t(`language.${lang}`)}
          </option>
        ))}
      </select>
    </div>
  )
}
