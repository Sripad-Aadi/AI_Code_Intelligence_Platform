import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { chat } from '../api/client'
import type { ChatMessage, EvidenceChunk } from '../api/types'
import { usePageTitle } from '../hooks/usePageTitle'
import BackButton from '../components/BackButton'

function EvidencePanel({ evidence }: { evidence: EvidenceChunk[] }) {
  if (evidence.length === 0) return null

  return (
    <details className="card mt-3">
      <summary className="cursor-pointer p-3 text-sm font-semibold text-stone-700 hover:text-stone-900">
        Evidence ({evidence.length} chunks)
      </summary>
      <div className="divide-y divide-stone-100 p-3">
        {evidence.map((e, i) => (
          <div key={i} className="py-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="badge badge-stone font-mono">{e.file_path}</span>
              {e.symbol_name && (
                <span className="badge badge-teal">{e.symbol_kind} {e.symbol_name}</span>
              )}
              <span className="badge badge-stone font-mono">lines {e.start_line}–{e.end_line}</span>
            </div>
            <pre className="max-h-48 overflow-auto rounded-lg bg-stone-50 p-3 font-mono text-xs text-stone-700 border border-stone-100">
              {e.content}
            </pre>
          </div>
        ))}
      </div>
    </details>
  )
}

type ChatTurn = ChatMessage & { evidence?: EvidenceChunk[] }

export default function Chat() {
  const { repoId } = useParams()
  const storageKey = `chat-${repoId}`
  const [messages, setMessages] = useState<ChatTurn[]>(() => {
    try {
      const saved = sessionStorage.getItem(storageKey)
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  })
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  usePageTitle('Chat')

  // Persist messages to sessionStorage (cleared when browser closes)
  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(messages))
    } catch {
      // storage full or unavailable
    }
  }, [messages, storageKey])

  const mutation = useMutation({
    mutationFn: (req: { repo_id: string; query: string; chat_history: ChatMessage[] }) =>
      chat(req),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer, evidence: data.evidence },
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
      <div className="flex items-start gap-3">
        <BackButton />
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight text-stone-900">Repository Chat</h1>
          <p className="mt-1 text-sm text-stone-500">
            Ask questions about the codebase. Answers are grounded in retrieved code with citations.
          </p>
        </div>
        <div className="group relative">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-full text-stone-400 hover:bg-stone-100 hover:text-stone-600"
            aria-label="About chat storage"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
          <div className="pointer-events-none absolute right-0 top-full z-10 mt-2 w-72 opacity-0 transition-opacity group-hover:opacity-100">
            <div className="card p-3 text-xs text-stone-600 shadow-lg">
              <p className="font-semibold text-stone-900">Note</p>
              <p className="mt-1">
                Chats are stored in your browser session and will be cleared when you log out or close the browser.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="card flex h-[70vh] flex-col">
        <div className="flex-1 space-y-4 overflow-auto p-6">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-teal-50">
                <svg className="h-8 w-8 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-stone-900">Start a conversation</h3>
              <p className="mt-2 max-w-sm text-sm text-stone-500">
                Ask about architecture, authentication, data flow, or any code in this repository.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {['How does authentication work?', 'What does the ingest_repo task do?', 'How is the database structured?'].map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-xs text-stone-600 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700"
                    onClick={() => {
                      setInput(q)
                      // Submit immediately — the user clicked a suggestion, so
                      // they want the answer, not just a filled input box.
                      const userMsg: ChatMessage = { role: 'user', content: q }
                      setMessages((prev) => [...prev, userMsg])
                      setInput('')
                      setIsLoading(true)
                      mutation.mutate({
                        repo_id: repoId as string,
                        query: q,
                        chat_history: messages,
                      })
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
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
                      ? 'rounded-2xl rounded-tr-none bg-teal-600 text-white p-4'
                      : 'rounded-2xl rounded-tl-none bg-stone-100 text-stone-900 p-4'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
                {msg.role === 'assistant' && msg.evidence && (
                  <EvidencePanel evidence={msg.evidence} />
                )}
              </div>
            ))
          )}
          {isLoading && (
            <div className="flex justify-center py-4">
              <div className="flex items-center gap-2 text-stone-500">
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" />
                <span className="text-sm">Thinking…</span>
              </div>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t border-stone-200 p-4">
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
