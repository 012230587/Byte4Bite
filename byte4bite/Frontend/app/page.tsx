import Link from 'next/link';

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <section className="mx-auto flex min-h-[calc(100vh-72px)] max-w-7xl flex-col justify-center px-6 py-16 sm:px-8 lg:px-12">
        <div className="grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div className="space-y-8">
            <p className="text-sm uppercase tracking-[0.32em] text-emerald-600">Recipe intelligence</p>
            <h1 className="text-5xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-6xl">
              Cook smarter with AI-powered recipe search and generation.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-slate-600">
              Turn your ingredients into a polished recipe experience. Discover dataset matches, generate custom meals, and follow professional cooking directions with a clean dashboard.
            </p>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center rounded-3xl bg-emerald-600 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-emerald-200 transition hover:bg-emerald-700"
              >
                Open Dashboard
              </Link>
            </div>
          </div>

          <div className="rounded-[2rem] bg-gradient-to-br from-emerald-600 to-cyan-600 p-8 text-white shadow-2xl shadow-emerald-200">
            <div className="space-y-5">
              <div className="rounded-3xl bg-white/10 p-6">
                <p className="text-sm uppercase tracking-[0.28em] text-white/80">Instant results</p>
                <p className="mt-3 text-3xl font-semibold">Search recipes by ingredient</p>
              </div>
              <div className="rounded-3xl bg-white/10 p-6">
                <p className="text-sm uppercase tracking-[0.28em] text-white/80">Custom meals</p>
                <p className="mt-3 text-3xl font-semibold">Generate chef-crafted recipes from pantry staples.</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}