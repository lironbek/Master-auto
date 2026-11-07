// Real brand marks (simple-icons, CC0) for the providers and channels the
// control center talks to. Falls back to null so callers can show a generic icon.
import { siClaude, siGithub, siGmail, siGooglegemini, siN8n, siOpenai, siSupabase, siTelegram, siVercel, siWhatsapp, type SimpleIcon } from 'simple-icons'

const icons: Record<string, SimpleIcon> = {
  whatsapp: siWhatsapp, telegram: siTelegram, github: siGithub, vercel: siVercel, supabase: siSupabase, n8n: siN8n,
  claude: siClaude, anthropic: siClaude, gemini: siGooglegemini, openai: siOpenai, email: siGmail, gmail: siGmail,
}

export function hasBrand(name: string): boolean { return name in icons }
export function brandHex(name: string): string | undefined { return icons[name] ? `#${icons[name].hex}` : undefined }

export function BrandIcon({ name, className = 'h-4 w-4' }: { name: string; className?: string }) {
  const i = icons[name]
  if (!i) return null
  return <svg viewBox="0 0 24 24" className={className} fill="currentColor" role="img" aria-label={i.title}><path d={i.path} /></svg>
}

/** Rounded tile in the brand colour with the white logo inside (WhatsApp green, Telegram blue, ...). */
export function BrandTile({ name, size = 'md', title }: { name: string; size?: 'sm' | 'md' | 'lg'; title?: string }) {
  const hex = brandHex(name)
  if (!hex) return null
  const box = size === 'sm' ? 'h-6 w-6 rounded-md' : size === 'lg' ? 'h-10 w-10 rounded-xl' : 'h-8 w-8 rounded-lg'
  const icon = size === 'sm' ? 'h-3.5 w-3.5' : size === 'lg' ? 'h-5 w-5' : 'h-4 w-4'
  return <span className={`grid shrink-0 place-items-center text-white shadow-sm ${box}`} style={{ backgroundColor: hex }} title={title}><BrandIcon name={name} className={icon} /></span>
}
