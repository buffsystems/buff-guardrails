import { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Button,
  Callout,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Chip,
  ChipRow,
  Field,
  LanguageToggle,
  LocaleProvider,
  Spinner,
  Table,
  TabPanel,
  Tabs,
  Textarea,
  useLanguage,
} from '@buff/ui/react'
import { Shield, Sparkles } from 'lucide-react'
import { api, type MaskResult, type Preset, type RunResult } from './api.ts'
import { STRINGS } from './i18n.ts'
import { MaskedText } from './MaskedText.tsx'

type Tab = 'mask' | 'run'

export function App() {
  const { choice, locale, setChoice } = useLanguage()
  const t = STRINGS[locale]
  const [presets, setPresets] = useState<Preset[]>([])
  const [preset, setPreset] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [task, setTask] = useState('')
  const [tab, setTab] = useState<Tab>('mask')
  const [modelOn, setModelOn] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [masked, setMasked] = useState<MaskResult | null>(null)
  const [run, setRun] = useState<RunResult | null>(null)

  useEffect(() => {
    api.presets().then((p) => setPresets(p.presets)).catch(() => setPresets([]))
    api.config().then((c) => setModelOn(c.model)).catch(() => setModelOn(false))
  }, [])

  // Prefill: a chosen set fills the text and the task in the current language; the text stays editable.
  useEffect(() => {
    const p = presets.find((x) => x.id === preset)
    if (!p) return
    setText(p.text[locale])
    setTask(p.task[locale])
    setMasked(null)
    setRun(null)
  }, [preset, locale, presets])

  const tabs = useMemo(
    () => [
      { id: 'mask', label: t.tabMask, icon: Shield },
      { id: 'run', label: t.tabRun, icon: Sparkles, disabled: !modelOn },
    ],
    [t, modelOn],
  )

  async function doMask() {
    setBusy(true)
    setError(null)
    try {
      setMasked(await api.mask(text, 'auto'))
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  async function doRun() {
    setBusy(true)
    setError(null)
    try {
      const r = await api.run(text, 'auto', task)
      setRun(r)
      setMasked(r)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <LocaleProvider locale={locale}>
      <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4 md:p-8">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">{t.title}</h1>
            <p className="text-muted-foreground mt-1 max-w-2xl">{t.subtitle}</p>
          </div>
          <LanguageToggle choice={choice} onChange={setChoice} label={t.language} />
        </header>

        <ChipRow label={t.presets}>
          {presets.map((p) => (
            <Chip key={p.id} pressed={preset === p.id} onClick={() => setPreset(p.id)} data-testid={`preset-${p.id}`}>
              {p.title[locale]}
            </Chip>
          ))}
        </ChipRow>

        <Card>
          <CardContent className="flex flex-col gap-3 pt-4">
            <Field label={t.input} hint={t.inputHint}>
              <Textarea
                rows={8}
                value={text}
                onChange={(e) => setText(e.target.value)}
                data-testid="source"
                spellCheck={false}
              />
            </Field>
            <Tabs items={tabs} value={tab} onValueChange={(id) => setTab(id as Tab)} variant="pill" label="mode">
              <TabPanel value="mask" className="flex flex-col gap-3 pt-3">
                <div>
                  <Button onClick={doMask} loading={busy} disabled={!text.trim()} data-testid="mask">
                    {t.mask}
                  </Button>
                </div>
              </TabPanel>
              <TabPanel value="run" className="flex flex-col gap-3 pt-3">
                <Field label={t.task}>
                  <Textarea rows={2} value={task} onChange={(e) => setTask(e.target.value)} data-testid="task" />
                </Field>
                <div>
                  <Button onClick={doRun} loading={busy} disabled={!text.trim()} data-testid="run">
                    {t.run}
                  </Button>
                </div>
              </TabPanel>
            </Tabs>
            {!modelOn && <Callout tone="info" compact>{t.noModel}</Callout>}
            {error && (
              <Callout tone="crit" title={t.error} role="alert">
                {error}
              </Callout>
            )}
          </CardContent>
        </Card>

        {busy && !masked && <Spinner />}

        {masked && (
          <Card>
            <CardHeader action={<Badge tone="neutral">{t.analyzerMs}: {masked.analyzer_ms} ms</Badge>}>
              <CardTitle>{t.masked}</CardTitle>
            </CardHeader>
            <CardContent>
              <MaskedText text={masked.masked} />
            </CardContent>
          </Card>
        )}

        {masked && (
          <Card>
            <CardHeader>
              <CardTitle>
                {t.found} <Badge tone="primary">{masked.entities.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {masked.entities.length === 0 ? (
                <p className="text-muted-foreground">{t.nothing}</p>
              ) : (
                <Table compact>
                  <thead>
                    <tr>
                      <th>{t.type}</th>
                      <th>{t.original}</th>
                      <th>{t.placeholder}</th>
                      <th className="ui-table__num">{t.score}</th>
                    </tr>
                  </thead>
                  <tbody data-testid="entities">
                    {masked.entities.map((e, i) => (
                      <tr key={i} data-type={e.type}>
                        <td>
                          <Badge tone="info" size="sm">
                            {e.type}
                          </Badge>
                        </td>
                        <td className="font-mono text-sm">{e.original}</td>
                        <td>
                          <span className="gr-mark">{e.placeholder}</span>
                        </td>
                        <td className="ui-table__num">{e.score.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}

        {run && (
          <>
            <Card>
              <CardHeader action={<Badge tone="neutral">{run.model}</Badge>}>
                <CardTitle>{t.prompt}</CardTitle>
              </CardHeader>
              <CardContent>
                <MaskedText text={run.prompt} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader action={<Badge tone="neutral">{t.modelMs}: {run.model_ms} ms</Badge>}>
                <CardTitle>{t.rawAnswer}</CardTitle>
              </CardHeader>
              <CardContent>
                <MaskedText text={run.raw_answer} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>{t.answer}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="gr-text" data-testid="answer">
                  {run.answer}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </LocaleProvider>
  )
}
