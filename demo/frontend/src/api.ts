export interface Entity {
  type: string
  start: number
  end: number
  score: number
  original: string
  placeholder: string
}

export interface MaskResult {
  masked: string
  entities: Entity[]
  mapping: Record<string, string>
  analyzer_ms: number
}

export interface RunResult extends MaskResult {
  prompt: string
  raw_answer: string
  answer: string
  model_ms: number
  model: string
}

export interface Preset {
  id: string
  title: Record<'ru' | 'en', string>
  text: Record<'ru' | 'en', string>
  expect: string[]
  task: Record<'ru' | 'en', string>
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = (await res.json()) as T & { error?: string }
  if (!res.ok) throw new Error(data.error ?? `${res.status}`)
  return data
}

export const api = {
  config: () => fetch('/api/config').then((r) => r.json() as Promise<{ model: boolean; model_name: string }>),
  presets: () => fetch('/api/presets').then((r) => r.json() as Promise<{ presets: Preset[] }>),
  mask: (text: string, language: string) => post<MaskResult>('/api/mask', { text, language }),
  run: (text: string, language: string, task: string) => post<RunResult>('/api/run', { text, language, task }),
}
