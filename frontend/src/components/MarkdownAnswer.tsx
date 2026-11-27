import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import type { Source } from '../services/types'

function normalizeMarkdownWithMath(raw: string): string {
  const normalizedDelims = raw
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, body) => `\n\n$$${body}$$\n\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, body) => `$${body}$`)

  // Give inline formulas with fractions full display spacing on their own breathable math card
  const expandedFractions = normalizedDelims.replace(
    /(?<!\$)\$(?!\$)([^\n$]*\\frac[^\n$]*)\$(?!\$)/g,
    (_, body) => `\n\n$$\n${body.trim()}\n$$\n\n`
  )

  return expandedFractions.replace(/\[(\d+)\](?!\()/g, '[$1](#cite-$1)')
}

export default function MarkdownAnswer({
  content,
  sources,
  onOpenSource,
  className = 'prose-um',
}: {
  content: string
  sources?: Source[]
  onOpenSource: (s: Source) => void
  className?: string
}) {
  const formatted = normalizeMarkdownWithMath(content)

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
        urlTransform={(u) => u}
        components={{
          a: ({ href, children }) => {
            const n = href?.startsWith('#cite-') ? Number(href.slice(6)) : 0
            const s = sources?.find((x) => x.n === n)
            return n ? (
              <button
                type="button"
                disabled={!s}
                onClick={() => s && onOpenSource(s)}
                aria-label={`Source ${n}`}
                title={s ? `${s.docTitle}, p. ${s.page}` : `Citation ${n}`}
                className="inline-flex items-center justify-center text-[11px] font-semibold px-1.5 py-0.5 mx-0.5 rounded bg-accent-tint text-accent hover:bg-accent hover:text-accent-ink leading-none align-baseline transition-colors"
              >
                {n}
              </button>
            ) : (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-ink hover:opacity-80 underline underline-offset-2"
              >
                {children}
              </a>
            )
          },
        }}
      >
        {formatted}
      </ReactMarkdown>
    </div>
  )
}
