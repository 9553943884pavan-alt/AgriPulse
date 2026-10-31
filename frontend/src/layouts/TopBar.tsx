/**
 * TopBar — full-width scenic landscape photo banner (120px tall).
 * Uses a real countryside photo: green fields, mountains, warm morning light.
 * Controls (bell, language, avatar) float top-right with glass backgrounds.
 */

import { LanguagePicker } from '@/components/LanguagePicker'
import { Bell } from 'lucide-react'

export function TopBar() {
  return (
    <header className="relative flex-shrink-0 z-20 overflow-hidden" style={{ height: 120 }}>
      {/* Real landscape photo — cover crop, centered */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: 'url(/banner-landscape.jpg)',
          backgroundSize: 'cover',
          backgroundPosition: 'center 60%',
          backgroundRepeat: 'no-repeat',
        }}
        aria-hidden="true"
      />

      {/* Subtle warm overlay to soften + maintain readability */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'linear-gradient(to bottom, rgba(0,0,0,0.08) 0%, rgba(0,0,0,0.18) 100%)',
        }}
        aria-hidden="true"
      />

      {/* Left-side dark overlay where sidebar meets banner */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'linear-gradient(to right, rgba(6,78,59,0.22) 0%, rgba(6,78,59,0.06) 20%, transparent 40%)',
        }}
        aria-hidden="true"
      />

      {/* Controls — top-right */}
      <div className="absolute top-0 right-0 h-full flex items-center px-5 gap-3">
        <button
          type="button"
          aria-label="Notifications"
          className="w-9 h-9 rounded-full flex items-center justify-center transition-colors hover:bg-black/20"
          style={{ background: 'rgba(255,255,255,0.4)', border: '1.5px solid rgba(255,255,255,0.65)', backdropFilter: 'blur(8px)' }}
        >
          <Bell className="w-4 h-4 text-gray-700" aria-hidden="true" />
        </button>

        <div
          className="flex items-center rounded-full px-2"
          style={{ background: 'rgba(255,255,255,0.5)', border: '1.5px solid rgba(255,255,255,0.7)', backdropFilter: 'blur(8px)' }}
        >
          <LanguagePicker />
        </div>

        <button
          type="button"
          aria-label="User profile"
          className="w-9 h-9 rounded-full flex items-center justify-center overflow-hidden transition-colors hover:bg-black/20"
          style={{ background: 'rgba(255,255,255,0.4)', border: '1.5px solid rgba(255,255,255,0.65)', backdropFilter: 'blur(8px)' }}
        >
          <span className="text-lg" aria-hidden="true">👤</span>
        </button>
      </div>
    </header>
  )
}
