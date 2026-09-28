import { useMutation } from '@tanstack/react-query'
import { Bot, Send, ShieldCheck, Sparkles, User } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import { ErrorBox, Spinner } from '../components/ui'
import { errorText, post } from '../lib/api'

type Msg = { role: 'user' | 'bot'; text: string; meta?: any; sources?: any[]; follow?: string[] }

const STARTERS = [
  'Compare Velachery and Tambaram for our next store',
  'Where are the best un-scouted opportunities?',
  'How is our property pipeline looking?',
  'Compare Anna Nagar, Kolathur and Porur',
]

export default function Assistant() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [q, setQ] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const ask = useMutation({
    mutationFn: (question: string) => post('/api/assistant/ask', { question }),
    onSuccess: (r) => setMsgs((m) => [...m, { role: 'bot', text: r.answer, meta: r.meta, sources: r.sources, follow: r.follow_ups }]),
  })
  useEffect(() => end.current?.scrollIntoView({ behavior: 'smooth' }), [msgs, ask.isPending])

  function send(text: string) {
    if (!text.trim() || ask.isPending) return
    setMsgs((m) => [...m, { role: 'user', text }])
    setQ('')
    ask.mutate(text)
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-57px-64px)] max-w-3xl flex-col md:h-[calc(100vh-57px)]">
      <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
        {!msgs.length && (
          <div className="pt-6 text-center">
            <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-savo-600 text-sun"><Bot className="h-7 w-7" /></div>
            <h1 className="text-2xl font-extrabold">Ask the analyst</h1>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
              Answers are computed live from our scoring model, reports, properties and surveys — the AI only phrases them, and every number it writes is checked against the data.
            </p>
            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              {STARTERS.map((s) => <button key={s} className="rounded-2xl border border-slate-200 bg-white p-3 text-left text-sm hover:border-savo-300" onClick={() => send(s)}>{s}</button>)}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex gap-2'}>
            {m.role === 'bot' && <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-savo-600 text-sun"><Bot className="h-4 w-4" /></div>}
            <div className={m.role === 'user' ? 'max-w-[85%] rounded-2xl rounded-br-md bg-savo-600 px-4 py-2 text-white' : 'min-w-0 max-w-[92%] rounded-2xl rounded-tl-md bg-white p-4 shadow-sm ring-1 ring-slate-200'}>
              {m.role === 'user' ? m.text : (
                <>
                  <div className="md max-w-none overflow-x-auto text-sm [&_table]:w-full [&_table]:text-xs [&_td]:border-t [&_td]:py-1 [&_td]:pr-2 [&_th]:pr-2 [&_th]:text-left">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t pt-2 text-[11px]">
                    {m.meta?.mode === 'ai'
                      ? <span className="chip bg-emerald-50 text-emerald-700"><ShieldCheck className="h-3 w-3" /> {m.meta.grounding?.numbers_cited} figures verified</span>
                      : <span className="chip bg-slate-100 text-slate-600" title={m.meta?.reason}><Sparkles className="h-3 w-3" /> Straight from the data</span>}
                    {m.sources?.map((s: any, j: number) => (
                      s.type === 'property' ? <Link key={j} to={`/properties/${s.id}`} className="chip bg-savo-50 text-savo-700">{s.label}</Link>
                        : s.type === 'study' ? <Link key={j} to={`/studies/${s.id}`} className="chip bg-savo-50 text-savo-700">{s.label}</Link>
                          : <span key={j} className="chip bg-slate-50 text-slate-500">{s.label}</span>
                    ))}
                  </div>
                  {m.follow && m.follow.length > 0 && i === msgs.length - 1 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">{m.follow.map((f) => <button key={f} className="rounded-full border border-savo-200 px-3 py-1 text-xs text-savo-700 hover:bg-savo-50" onClick={() => send(f)}>{f}</button>)}</div>
                  )}
                </>
              )}
            </div>
            {m.role === 'user' && <div className="ml-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200"><User className="h-4 w-4" /></div>}
          </div>
        ))}
        {ask.isPending && <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner className="h-4 w-4" /> Crunching the numbers…</div>}
        {ask.error && <ErrorBox error={errorText(ask.error)} />}
        <div ref={end} />
      </div>
      <form className="flex gap-2 border-t bg-white p-3" onSubmit={(e) => { e.preventDefault(); send(q) }}>
        <input className="input" placeholder="e.g. compare Velachery and Tambaram for our next store" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn-primary" disabled={!q.trim() || ask.isPending}><Send className="h-4 w-4" /></button>
      </form>
    </div>
  )
}
