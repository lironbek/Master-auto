// Drop-in usage reporter for your own apps (Next.js / Vite server code / Node).
// Copy this file into the app, set three env vars, and call reportUsage() right
// after every paid call. Fire-and-forget: it never throws and never blocks.
//
//   CC_USAGE_URL=https://master-auto-lake.vercel.app/api/cc/usage
//   CC_REPORT_TOKEN=<workspace reporter token, from "חיבורים">
//   CC_WORKSPACE_ID=<workspace id>

export type UsageEntry = {
  provider: 'claude' | 'gemini' | 'openai' | 'ocr' | 'whatsapp' | 'telegram' | 'sms' | 'email' | 'other'
  metric: 'requests' | 'tokens_in' | 'tokens_out' | 'tokens_cached' | 'messages' | 'recipients' | 'pages' | 'characters' | 'minutes' | 'units'
  quantity: number
  interface: string            // which app/feature made the call, e.g. "crm/quote-bot"
  client?: string              // client name (created on first use) ...
  client_id?: string           // ... or its id
  project_id?: string
  model?: string
  recipients?: number          // WhatsApp: how many people this batch reached
  external_id?: string         // unique per call -> a retry is not counted twice
  occurred_at?: string
  meta?: Record<string, unknown>
}

export function reportUsage(entries: UsageEntry[]): void {
  const url = process.env.CC_USAGE_URL, token = process.env.CC_REPORT_TOKEN, ws = process.env.CC_WORKSPACE_ID
  if (!url || !token || !ws || entries.length === 0) return
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Report-Token': token },
    body: JSON.stringify({ workspace_id: ws, entries }),
  }).catch(() => { /* never let metering break the product */ })
}

// --- examples --------------------------------------------------------------

// Claude (Anthropic SDK): report the request and the tokens the API returned.
export function reportClaude(client: string, iface: string, model: string, usage: { input_tokens: number; output_tokens: number }, callId: string) {
  reportUsage([
    { provider: 'claude', metric: 'requests', quantity: 1, interface: iface, client, model, external_id: `${callId}:req` },
    { provider: 'claude', metric: 'tokens_in', quantity: usage.input_tokens, interface: iface, client, model, external_id: `${callId}:in` },
    { provider: 'claude', metric: 'tokens_out', quantity: usage.output_tokens, interface: iface, client, model, external_id: `${callId}:out` },
  ])
}

// Gemini: usageMetadata.promptTokenCount / candidatesTokenCount.
export function reportGemini(client: string, iface: string, model: string, usage: { promptTokenCount: number; candidatesTokenCount: number }, callId: string) {
  reportUsage([
    { provider: 'gemini', metric: 'requests', quantity: 1, interface: iface, client, model, external_id: `${callId}:req` },
    { provider: 'gemini', metric: 'tokens_in', quantity: usage.promptTokenCount, interface: iface, client, model, external_id: `${callId}:in` },
    { provider: 'gemini', metric: 'tokens_out', quantity: usage.candidatesTokenCount, interface: iface, client, model, external_id: `${callId}:out` },
  ])
}

// WhatsApp (Meta Cloud API / Twilio / Green API): one entry per send batch.
export function reportWhatsApp(client: string, iface: string, messages: number, recipients: number, batchId: string) {
  reportUsage([{ provider: 'whatsapp', metric: 'messages', quantity: messages, recipients, interface: iface, client, external_id: `wa:${batchId}` }])
}

// OCR: pages processed for a document.
export function reportOcr(client: string, iface: string, pages: number, documentId: string) {
  reportUsage([{ provider: 'ocr', metric: 'pages', quantity: pages, interface: iface, client, external_id: `ocr:${documentId}` }])
}
