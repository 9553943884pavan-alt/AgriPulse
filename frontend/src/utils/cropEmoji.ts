/**
 * Maps crop_id → a representative emoji.
 * Used everywhere a crop icon is shown (Dashboard, Home preview, Comparison).
 * Fallback to 🌾 for unknown crops.
 */
export const CROP_EMOJI: Record<string, string> = {
  // Cereals
  wheat:       '🌾',
  rice:        '🌾',
  maize:       '🌽',
  jowar:       '🌿',   // sorghum — no dedicated emoji, millet-like
  bajra:       '🌿',   // pearl millet
  ragi:        '🌿',

  // Pulses
  chickpea:    '🫘',
  pigeonpea:   '🫘',
  lentil:      '🫘',
  moong:       '🫘',
  urad:        '🫘',
  soybean:     '🫘',

  // Oilseeds
  groundnut:   '🥜',
  sunflower:   '🌻',
  mustard:     '🌼',
  sesame:      '🌼',
  safflower:   '🌼',

  // Vegetables
  onion:       '🧅',
  tomato:      '🍅',
  potato:      '🥔',
  garlic:      '🧄',
  cabbage:     '🥬',
  cauliflower: '🥦',
  brinjal:     '🍆',
  chilli:      '🌶️',
  okra:        '🫑',
  peas:        '🫛',

  // Fruits
  banana:      '🍌',
  mango:       '🥭',
  pomegranate: '🍎',
  grapes:      '🍇',
  orange:      '🍊',
  papaya:      '🍈',

  // Cash crops
  cotton:      '🪴',
  sugarcane:   '🎋',
  turmeric:    '🟡',
}

/** Returns the emoji for a crop_id, falling back to 🌾. */
export function getCropEmoji(cropId: string): string {
  return CROP_EMOJI[cropId.toLowerCase()] ?? '🌾'
}
