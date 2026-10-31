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
      <Globe className="w-4 h-4 text-fresh-leaf absolute left-3 pointer-events-none" aria-hidden="true" />
      <select
        value={language}
        onChange={(e) => handleChange(e.target.value as Language)}
        aria-label="Select language"
        className="
          pl-9 pr-6 py-1.5 rounded-full text-xs font-semibold bg-white border border-sage-mist
          text-forest appearance-none cursor-pointer shadow-xs transition-colors
          hover:bg-sage-mist/20 focus:outline-none focus:ring-2 focus:ring-fresh-leaf
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
