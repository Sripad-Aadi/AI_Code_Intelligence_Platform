import { Link } from 'react-router-dom'
import { usePageTitle } from '../hooks/usePageTitle'

const features = [
  {
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
      </svg>
    ),
    title: 'Link GitHub',
    description: 'Connect your GitHub account to access your repositories.',
  },
  {
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    ),
    title: 'Clone & Analyze',
    description: 'We clone your repo and extract symbols, imports, and structure.',
  },
  {
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
    title: 'Semantic Search',
    description: 'Ask questions in natural language and get answers with code citations.',
  },
  {
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: 'Code Intelligence',
    description: 'Explore file structure, symbols, and import relationships visually.',
  },
  {
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    title: 'AI Chat',
    description: 'Ask questions about your codebase and get grounded answers.',
  },
  {
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    title: 'PR Analysis',
    description: 'Analyze pull requests for impact, affected files, and risks.',
  },
]

export default function Landing() {
  usePageTitle('AI Software Intelligence')

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-stone-100">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-600 text-white">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <span className="text-lg font-bold tracking-tight text-stone-900">
              AI Software Intelligence
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="btn btn-ghost">Sign in</Link>
            <Link to="/login?mode=signup" className="btn btn-primary">Get started</Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-teal-50 via-white to-amber-50" />
        <div className="relative mx-auto max-w-6xl px-4 py-24 text-center">
          <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-4 py-1.5 text-sm font-medium text-teal-700">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            AI-Powered Code Intelligence
          </div>
          <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight text-stone-900 sm:text-5xl lg:text-6xl">
            Your entire codebase,{' '}
            <span className="text-teal-600">at your fingertips</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-stone-600">
            Link your GitHub, clone your repo, and analyze it — get semantic search,
            AI-powered chat, and deep code insights in minutes.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link to="/login?mode=signup" className="btn btn-primary px-6 py-3 text-base">
              Get started free
            </Link>
            <Link to="/login" className="btn btn-outline px-6 py-3 text-base">
              Sign in
            </Link>
          </div>
          <p className="mt-4 text-sm text-stone-500">
            No credit card required • Free tier available
          </p>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-stone-100 bg-stone-50">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-center text-3xl font-bold tracking-tight text-stone-900">
            How it works
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-stone-600">
            Three simple steps to unlock your codebase's potential
          </p>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {[
              { step: '01', title: 'Link GitHub', desc: 'Connect your GitHub account with one click. We\'ll list all your repositories.' },
              { step: '02', title: 'Clone & Analyze', desc: 'Pick a repo and we\'ll clone it, parse the structure, and embed the code for search.' },
              { step: '03', title: 'Explore & Ask', desc: 'Search semantically, chat with AI, and explore your code like never before.' },
            ].map((item) => (
              <div key={item.step} className="card p-6">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-100 text-sm font-bold text-teal-700">
                  {item.step}
                </div>
                <h3 className="mt-4 text-lg font-semibold text-stone-900">{item.title}</h3>
                <p className="mt-2 text-sm text-stone-600">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-stone-100">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-center text-3xl font-bold tracking-tight text-stone-900">
            Everything you need
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-stone-600">
            Powerful features to understand and navigate your codebase
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div key={f.title} className="card p-6">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-50 text-teal-600">
                  {f.icon}
                </div>
                <h3 className="mt-4 text-base font-semibold text-stone-900">{f.title}</h3>
                <p className="mt-2 text-sm text-stone-600">{f.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-stone-100 bg-teal-600">
        <div className="mx-auto max-w-6xl px-4 py-16 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white">
            Ready to explore your codebase?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-teal-100">
            Join developers who are already using AI to understand their code better.
          </p>
          <div className="mt-8">
            <Link to="/login?mode=signup" className="btn bg-white px-6 py-3 text-base text-teal-700 hover:bg-teal-50">
              Get started now
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-stone-100 bg-stone-900">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-600 text-white">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <span className="text-sm font-semibold text-white">AI Software Intelligence</span>
            </div>
            <div className="flex gap-6 text-sm text-stone-400">
              <Link to="/login" className="hover:text-white">Sign in</Link>
              <Link to="/login?mode=signup" className="hover:text-white">Get started</Link>
            </div>
          </div>
          <div className="mt-8 border-t border-stone-800 pt-8 text-center text-xs text-stone-500">
            Built with FastAPI, React, and AI • Powered by Supabase and Groq
          </div>
        </div>
      </footer>
    </div>
  )
}
