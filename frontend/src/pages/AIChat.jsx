import { useState, useRef, useEffect } from 'react'
import { Send, Zap } from 'lucide-react'

const QUICK_ACTIONS = [
  { id: 'pause', label: 'Что остановить?', icon: '⏸' },
  { id: 'scale', label: 'Что масштабировать?', icon: '📈' },
  { id: 'budget', label: 'Анализ бюджета', icon: '💰' },
  { id: 'strategy', label: 'Стратегия роста', icon: '🚀' },
]

const PROMPTS = {
  pause: 'Какие ключевые слова нужно остановить прямо сейчас? Перечисли с суммой трат и причиной.',
  scale: 'Какие ключи и кампании можно масштабировать? Дай конкретные ставки и бюджеты.',
  budget: 'Где я теряю бюджет? Посчитай общие потери и дай план экономии.',
  strategy: 'Предложи стратегию роста на следующий месяц. Учти текущие данные.',
}

export default function AIChat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text) => {
    if (!text.trim() || streaming) return
    const userMsg = { role: 'user', content: text }
    setMessages((prev) => [...prev, userMsg, { role: 'assistant', content: '' }])
    setInput('')
    setStreaming(true)

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6))
              if (parsed.token) {
                setMessages((prev) => {
                  const updated = [...prev]
                  const last = updated[updated.length - 1]
                  if (last.role === 'assistant') {
                    updated[updated.length - 1] = { ...last, content: last.content + parsed.token }
                  }
                  return updated
                })
              }
            } catch {}
          }
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: `❌ Ошибка подключения к Ollama: ${e.message}\n\nЗапустите: ollama serve`,
        }
        return updated
      })
    }

    setStreaming(false)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-100px)]">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2 pb-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-6 animate-in">
            <Zap className="w-10 h-10" style={{ color: 'var(--accent-primary)', opacity: 0.3 }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
              AI ассистент Amazon PPC. Задайте вопрос или выберите быстрое действие.
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {QUICK_ACTIONS.map((qa) => (
                <button
                  key={qa.id}
                  onClick={() => sendMessage(PROMPTS[qa.id])}
                  className="px-4 py-2 rounded-xl text-sm font-body transition-all border
                             border-accent-primary/15 text-white/60 hover:border-accent-primary/30
                             hover:bg-accent-primary/5 hover:text-white/80 active:scale-[0.97]"
                >
                  <span className="mr-1.5">{qa.icon}</span>{qa.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm font-body leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? ''
                  : 'border-l-2'
              }`}
              style={
                msg.role === 'user'
                  ? { background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)' }
                  : {
                      background: 'var(--glass-bg)', borderColor: 'var(--accent-primary)',
                      color: 'var(--text-primary)',
                    }
              }
            >
              {msg.content}
              {streaming && i === messages.length - 1 && msg.role === 'assistant' && (
                <span className="inline-block w-0.5 h-4 ml-0.5 bg-accent-primary animate-pulse" />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-3 pt-4 border-t" style={{ borderColor: 'var(--glass-border)' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage(input)}
          placeholder="Задайте вопрос AI ассистенту..."
          disabled={streaming}
          className="flex-1 px-4 py-3 rounded-xl text-sm font-body border transition-all
                     focus:outline-none focus:shadow-[0_0_0_2px_rgba(79,142,255,0.3)]
                     disabled:opacity-50"
          style={{
            background: 'var(--glass-bg)', borderColor: 'var(--glass-border)',
            color: 'var(--text-primary)',
          }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={streaming || !input.trim()}
          className="px-4 rounded-xl transition-all border border-accent-primary/30
                     text-accent-primary hover:bg-accent-primary/10 active:scale-[0.97]
                     disabled:opacity-30"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
