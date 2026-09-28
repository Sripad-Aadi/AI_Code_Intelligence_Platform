import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { chat } from '../api/client'
import type { ChatMessage, EvidenceChunk } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'

function EvidencePanel({ evidence }: { evidence: EvidenceChunk[] }) {
  if (evidence.length === 0) return null

  return (
    <details className="card mt-4">
      <summary className="font-semibold text-slate-700 cursor-pointer p-2">
        Evidence ({evidence.length} chunks)
      </summary>
      <div className="divide-y divide-slate-100 p-2">
        {evidence.map((e, i) => (
          <div key={i} className="py-2">
            <div className="flex flex-wrap items-center gap-2 text-xs mb-1">
              <span className="badge bg-slate-100 text-slate-600 font-mono">
                {e.file_path}
              </span>
              {e.symbol_name && (
                <span className="badge bg-indigo-100 text-indigo-700">
                  {e.symbol_kind} {e.symbol_name}
                </span>
              )}
              <span className="badge bg-slate-100 text-slate-500 font-mono">
                lines {e.start_line}–{e.end_line}
              </span>
            </div>
            <pre className="bg-slate-50 rounded p-2 overflow-auto text-xs font-mono text-slate-700 max-h-48">
              {e.content}
            </pre>
          </div>
        ))}
      </div>
    </details>
  )
}

export default function Chat() {
  const { repoId } = useParams()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  usePageTitle('Chat')

  const mutation = useMutation({
    mutationFn: (req: { repo_id: string; query: string; chat_history: ChatMessage[] }) =>
      chat(req),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer },
      ])
    },
    onError: (err: Error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}` },
      ])
    },
    onSettled: () => {
      setIsLoading(false)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMsg: ChatMessage = { role: 'user', content: input.trim() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    mutation.mutate({
      repo_id: repoId as string,
      query: userMsg.content,
      chat_history: messages,
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Repository Chat</h1>
        <p className="mt-1 text-sm text-slate-500">
          Ask questions about the codebase. Answers are grounded in retrieved code with citations.
        </p>
      </div>

      <div className="card flex flex-col h-[70vh]">
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="text-center text-slate-400 py-12">
              <p className="text-lg font-medium">Start a conversation</p>
              <p className="mt-1 text-sm">
                Try: "How does authentication work?" or "What does the ingest_repo task do?"
              </p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-3 ${msg.role === 'assistant' ? 'flex-col' : 'flex-row-reverse'}`}
              >
                <div
                  className={`max-w-[75%] ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-2xl rounded-tr-none p-3'
                      : 'bg-slate-100 text-slate-900 rounded-2xl rounded-tl-none p-3'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
                {/* Evidence panel for assistant messages */}
                {msg.role === 'assistant' && mutation.data?.evidence && (
                  <EvidencePanel evidence={mutation.data.evidence} />
                )}
              </div>
            ))
          )}
          {isLoading && (
            <div className="flex justify-center py-4">
              <div className="flex items-center gap-2 text-slate-500">
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
                <span className="text-sm">Thinking…</span>
              </div>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-slate-200 p-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the repository…"
              className="input flex-1"
              disabled={isLoading}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!input.trim() || isLoading}
            >
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}