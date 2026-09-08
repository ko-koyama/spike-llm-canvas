import { useState } from 'react'

type ApiBlock =
  | { type: 'text'; text: string }
  | { type: 'chart'; variant: string | null; html: string }
  | { type: 'map'; variant: string | null; html: string }

// チャット欄に積む表示用ブロック。可視化系はHTMLを直接持たず、vizIdで右ペインの実体を参照する
type DisplayBlock = { type: 'text'; text: string } | { type: 'viz-ref'; vizId: string }

type Message = {
  id: string
  role: 'user' | 'assistant'
  blocks: DisplayBlock[]
}

type VizType = 'chart' | 'map'

type Visualization = {
  id: string
  type: VizType
  variant: string | null
  html: string
}

const VIZ_TYPE_LABELS: Record<VizType, string> = { chart: 'グラフ', map: '地図' }

// チャート/地図の具体的な種別ラベル。未知のvariantの場合は種別の総称にフォールバックする
const VIZ_VARIANT_LABELS: Record<string, string> = {
  bar: '棒グラフ',
  line: '折れ線グラフ',
  scatter: '散布図',
  pie: '円グラフ',
  choropleth: 'コロプレスマップ',
  spider: 'スパイダーマップ',
}

function vizLabel(viz: Visualization): string {
  return (viz.variant && VIZ_VARIANT_LABELS[viz.variant]) || VIZ_TYPE_LABELS[viz.type]
}

// ページを開いている間だけ会話を続けるためのID。リロードで新しい会話になる。
const sessionId = crypto.randomUUID()

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [visualizations, setVisualizations] = useState<Visualization[]>([])
  const [activeVizId, setActiveVizId] = useState<string | null>(null)
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
      const data: { blocks: ApiBlock[] } = await res.json()

      const { displayBlocks, newVisualizations } = splitVisualizations(data.blocks)
      setVisualizations((prev) => [...prev, ...newVisualizations])
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'assistant', blocks: displayBlocks }])
      if (newVisualizations.length > 0) {
        setActiveVizId(newVisualizations[newVisualizations.length - 1].id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const activeViz = visualizations.find((v) => v.id === activeVizId) ?? null

  return (
    <div className="layout">
      <div className="chat-column">
        <div className="messages">
          {messages.map((m) => (
            <div key={m.id} className={`turn ${m.role}`}>
              {m.blocks.map((b, i) =>
                b.type === 'viz-ref' ? (
                  <VizCard
                    key={i}
                    viz={visualizations.find((v) => v.id === b.vizId) ?? null}
                    onOpen={() => setActiveVizId(b.vizId)}
                  />
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

      {activeViz && (
        <CanvasPanel
          visualizations={visualizations}
          activeViz={activeViz}
          onSelect={setActiveVizId}
          onClose={() => setActiveVizId(null)}
        />
      )}
    </div>
  )
}

// バックエンドから届いたブロック列を、チャット表示用ブロックとvisualizationに分離する
function splitVisualizations(blocks: ApiBlock[]): {
  displayBlocks: DisplayBlock[]
  newVisualizations: Visualization[]
} {
  const newVisualizations: Visualization[] = []
  const displayBlocks: DisplayBlock[] = blocks.map((b) => {
    if (b.type === 'text') return b
    const viz: Visualization = { id: crypto.randomUUID(), type: b.type, variant: b.variant, html: b.html }
    newVisualizations.push(viz)
    return { type: 'viz-ref', vizId: viz.id }
  })
  return { displayBlocks, newVisualizations }
}

function VizCard({ viz, onOpen }: { viz: Visualization | null; onOpen: () => void }) {
  if (!viz) return null
  return (
    <button type="button" className="viz-card" onClick={onOpen}>
      🔗 {vizLabel(viz)}を表示
    </button>
  )
}

function CanvasPanel({
  visualizations,
  activeViz,
  onSelect,
  onClose,
}: {
  visualizations: Visualization[]
  activeViz: Visualization
  onSelect: (id: string) => void
  onClose: () => void
}) {
  const activeIndex = visualizations.findIndex((v) => v.id === activeViz.id)

  return (
    <div className="canvas-panel">
      <div className="canvas-panel-header">
        <div className="canvas-panel-nav">
          <button
            type="button"
            disabled={activeIndex <= 0}
            onClick={() => onSelect(visualizations[activeIndex - 1].id)}
          >
            ← 前へ
          </button>
          <select value={activeIndex} onChange={(e) => onSelect(visualizations[Number(e.target.value)].id)}>
            {visualizations.map((v, i) => (
              <option key={v.id} value={i}>
                {i + 1}. {vizLabel(v)}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={activeIndex >= visualizations.length - 1}
            onClick={() => onSelect(visualizations[activeIndex + 1].id)}
          >
            次へ →
          </button>
        </div>
        <div className="canvas-panel-actions">
          <button type="button" className="canvas-panel-download" onClick={() => downloadViz(activeViz, activeIndex)}>
            ⬇ ダウンロード
          </button>
          <button type="button" className="canvas-panel-close" onClick={onClose}>
            ×
          </button>
        </div>
      </div>
      <div className="canvas-panel-body">
        <iframe className="canvas-frame" srcDoc={activeViz.html} sandbox="allow-scripts" />
      </div>
    </div>
  )
}

// 選択中の可視化のHTMLをファイルとしてダウンロードさせる
function downloadViz(viz: Visualization, index: number) {
  const blob = new Blob([viz.html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${index + 1}_${vizLabel(viz)}.html`
  a.click()
  URL.revokeObjectURL(url)
}
