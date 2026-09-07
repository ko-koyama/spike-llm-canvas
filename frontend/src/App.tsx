import { useState } from 'react'

type Block = { type: 'text'; text: string } | { type: 'chart'; html: string } | { type: 'map'; html: string }

type Message = {
  id: string
  role: 'user' | 'assistant'
  blocks: Block[]
}

// ページを開いている間だけ会話を続けるためのID。リロードで新しい会話になる。
const sessionId = crypto.randomUUID()

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send() {
    const message = input.trim()
    if (!message || loading) return

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', blocks: [{ type: 'text', text: message }] },
    ])
    setInput('')
    setError(null)
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data: { blocks: Block[] } = await res.json()
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', blocks: data.blocks }])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <div className="messages">
        {messages.map((m) => (
          <div key={m.id} className={`turn ${m.role}`}>
            {m.blocks.map((b, i) =>
              b.type === 'chart' || b.type === 'map' ? (
                <div key={i} className="chart-panel">
                  <iframe className={b.type} srcDoc={b.html} sandbox="allow-scripts" />
                </div>
              ) : (
                <div key={i} className={`msg ${m.role}`}>
                  {b.text}
                </div>
              ),
            )}
          </div>
        ))}
        {loading && <div className="msg assistant pending">考え中...</div>}
        {error && <div className="error">エラー: {error}</div>}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send()
            }
          }}
          placeholder="メッセージを入力(Enterで送信 / Shift+Enterで改行)"
          rows={2}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          送信
        </button>
      </form>
    </div>
  )
}
