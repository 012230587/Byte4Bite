import Link from "next/link";

export default function PromoSection() {
  return (
    <div className="relative overflow-hidden bg-white text-slate-950">
      <div className="pointer-events-none absolute inset-0 opacity-80">
        <div className="petal pink left-[12%] top-[18%] animate-drift-slow" />
        <div className="petal cyan left-[68%] top-[10%] animate-drift-fast" />
        <div className="petal light left-[45%] top-[30%] animate-drift-slow" />
        <div className="petal pink left-[80%] top-[60%] animate-drift-fast" />
        <div className="petal cyan left-[25%] top-[65%] animate-drift-slow" />
      </div>

      <section className="mx-auto flex max-w-6xl flex-col items-center justify-center gap-10 px-6 py-24 sm:px-10 lg:px-16">
        <div className="relative w-full max-w-3xl text-center">
          <p className="mb-6 text-sm uppercase tracking-[0.32em] text-slate-500">
            Modern meal planning
          </p>
          <h1 className="relative inline-block text-4xl font-display font-semibold leading-tight tracking-[-0.04em] text-slate-950 sm:text-5xl lg:text-6xl">
            Don&apos;t forget! One plan, all devices
          </h1>
          <span className="absolute right-0 top-0 -translate-y-12 text-xs uppercase tracking-[0.22em] text-slate-300 opacity-40 sm:text-sm">
            サインアップ
          </span>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-8 text-slate-600 sm:text-lg">
            Keep your weekly menu in sync across your phone, tablet, and laptop. One central plan means every device stays updated with the latest recipes, grocery lists, and cooking timelines.
          </p>
        </div>

        <div className="relative flex flex-col items-center gap-4">
          <div className="flex flex-col items-center gap-3 sm:flex-row">
            <Link
              href="/register"
              className="inline-flex items-center justify-center rounded-full bg-black px-8 py-4 text-sm font-semibold uppercase tracking-[0.22em] text-white transition duration-150 ease-out hover:bg-slate-900"
            >
              Register
            </Link>
            <Link
              href="/signin"
              className="inline-flex items-center justify-center rounded-full border border-black bg-white px-8 py-4 text-sm font-semibold uppercase tracking-[0.22em] text-black transition duration-150 ease-out hover:bg-slate-100"
            >
              Sign in
            </Link>
          </div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
            Access your recipes or create an account to save meal plans.
          </p>
        </div>
      </section>

      <div className="relative overflow-hidden bg-white">
        <svg viewBox="0 0 1440 140" className="h-[10rem] w-full" preserveAspectRatio="none" aria-hidden="true">
          <path
            d="M0,24 C200,98 320,12 540,52 C760,92 860,22 1080,54 C1220,78 1340,28 1440,44 L1440,140 L0,140 Z"
            fill="#0f172a"
          />
        </svg>
      </div>

      <footer className="bg-slate-950 text-slate-100">
        <div className="mx-auto flex max-w-6xl flex-col gap-12 px-6 py-20 sm:px-10 lg:px-16">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-4 text-center lg:text-left">
              <p className="font-brand text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                CookBook
              </p>
              <p className="max-w-xl text-sm leading-7 text-slate-400 sm:text-base">
                The CookBook App is brought to you by a team of recipe lovers and product designers building smarter meal planning for every kitchen.
              </p>
            </div>

            <div className="flex flex-col items-center gap-6 sm:items-end">
              <div className="flex flex-wrap items-center justify-center gap-3 sm:justify-end">
                <button
                  type="button"
                  aria-label="TikTok"
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-slate-950 transition hover:scale-[1.05]"
                >
                  <span className="sr-only">TikTok</span>
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
                    <path d="M9 3h3.3c0 3.3 2.7 6 6 6v3.3c-3.3 0-6 2.7-6 6-3.3 0-6-2.7-6-6V9c1.4 0 2.7.5 3.7 1.4V3Z" />
                  </svg>
                </button>
                <button
                  type="button"
                  aria-label="Facebook"
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-slate-950 transition hover:scale-[1.05]"
                >
                  <span className="sr-only">Facebook</span>
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
                    <path d="M15.12 3H12.7c-2.95 0-4.87 1.9-4.87 4.82v2.14H4.5C4.23 10 4 10.22 4 10.5v3.13c0 .28.23.5.5.5h3.33v7.53c0 .28.22.52.5.52h3.74c.28 0 .5-.24.5-.52v-7.52h3.2c.28 0 .5-.23.5-.5v-3.13a.5.5 0 0 0-.5-.5h-3.2V7.58c0-.95.23-1.43 1.45-1.43h1.73c.28 0 .5-.22.5-.5V3.5a.5.5 0 0 0-.5-.5Z" />
                  </svg>
                </button>
                <button
                  type="button"
                  aria-label="Instagram"
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-slate-950 transition hover:scale-[1.05]"
                >
                  <span className="sr-only">Instagram</span>
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                    <rect x="4" y="4" width="16" height="16" rx="4" />
                    <path d="M16 11.37a4 4 0 1 1-7.99.63 4 4 0 0 1 7.99-.63Z" />
                    <path d="M17.5 6.5h.01" />
                  </svg>
                </button>
              </div>

              <nav className="flex flex-wrap justify-center gap-4 text-sm font-medium text-slate-400 sm:justify-end">
                <a href="#" className="transition hover:text-white">Features</a>
                <a href="#" className="transition hover:text-white">Pricing</a>
                <a href="#" className="transition hover:text-white">Blog</a>
                <a href="#" className="transition hover:text-white">Support</a>
              </nav>
            </div>
          </div>
        </div>
      </footer>

      <div className="chat-widget fixed right-4 bottom-6 z-50 w-[280px] max-w-[90vw] animate-float-bubble">
        <div className="relative overflow-hidden rounded-[28px] border-[4px] border-black bg-slate-950 px-4 py-4 text-slate-100 shadow-[6px_6px_0_rgba(0,0,0,1)]">
          <div className="absolute -right-4 top-4 h-6 w-6 rotate-45 rounded-tl-[10px] border-[4px] border-black bg-slate-950" />
          <p className="text-[0.7rem] uppercase tracking-[0.3em] text-slate-400">Dialogue</p>
          <p className="mt-2 text-base font-semibold text-white">Need recipe advice?</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">Open the visual novel style helper for quick meal ideas and chef tips.</p>
        </div>
      </div>
    </div>
  );
}
