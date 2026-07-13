function App() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-950 text-slate-100">
      <h1 className="text-4xl font-semibold tracking-tight">Catalog</h1>
      <p className="mt-2 text-slate-400">ИИ-агент для аналитика — каркас готов</p>
      <div className="mt-6 flex gap-3">
        <span className="rounded-md bg-indigo-500/20 px-3 py-1 text-sm text-indigo-300">FastAPI</span>
        <span className="rounded-md bg-cyan-500/20 px-3 py-1 text-sm text-cyan-300">React + Vite</span>
        <span className="rounded-md bg-emerald-500/20 px-3 py-1 text-sm text-emerald-300">Tailwind</span>
      </div>
    </div>
  )
}

export default App
