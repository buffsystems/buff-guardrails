import { Fragment } from 'react'

const PLACEHOLDER = /<[A-Z_]+_\d+>/g

/** Text with `<TYPE_n>` placeholders rendered as marks. */
export function MaskedText({ text }: { text: string }) {
  const parts: Array<string | { mark: string }> = []
  let last = 0
  for (const m of text.matchAll(PLACEHOLDER)) {
    parts.push(text.slice(last, m.index), { mark: m[0] })
    last = (m.index ?? 0) + m[0].length
  }
  parts.push(text.slice(last))
  return (
    <div className="gr-text" data-testid="masked-text">
      {parts.map((p, i) =>
        typeof p === 'string' ? (
          <Fragment key={i}>{p}</Fragment>
        ) : (
          <span key={i} className="gr-mark">
            {p.mark}
          </span>
        ),
      )}
    </div>
  )
}
