import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Every preset is a regression test: pick it, mask, and check that each expected
// entity family shows up in the table and that no original value is left in the
// masked text. Runs against the stack from docker compose (DEMO_URL, default :8080).
const presetsFile = fileURLToPath(new URL('../../presets.json', import.meta.url))
const { presets } = JSON.parse(readFileSync(presetsFile, 'utf8')) as {
  presets: Array<{ id: string; expect: string[]; text: Record<'ru' | 'en', string> }>
}

for (const lang of ['ru', 'en'] as const) {
  for (const preset of presets) {
    test(`${lang}: preset ${preset.id} masks ${preset.expect.join(', ')}`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem('language', l), lang)
      await page.goto('/')
      await page.getByTestId(`preset-${preset.id}`).click()
      await expect(page.getByTestId('source')).toHaveValue(preset.text[lang])
      await page.getByTestId('mask').click()
      const rows = page.getByTestId('entities').locator('tr')
      await expect(rows.first()).toBeVisible({ timeout: 60_000 })
      const types = new Set(await rows.evaluateAll((trs) => trs.map((tr) => tr.getAttribute('data-type'))))
      for (const family of preset.expect) {
        expect(types, `${family} missing in ${preset.id}/${lang}`).toContain(family)
      }
      const masked = (await page.getByTestId('masked-text').textContent()) ?? ''
      const originals = await rows.locator('td:nth-child(2)').allTextContents()
      for (const value of originals) {
        expect(masked, `value left in masked text: ${value}`).not.toContain(value)
      }
    })
  }
}
