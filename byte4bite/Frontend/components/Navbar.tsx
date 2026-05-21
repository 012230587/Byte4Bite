import Link from "next/link";

const Navbar = () => {
  return (
    <nav className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/95 backdrop-blur-xl shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-3 text-lg font-semibold text-slate-900">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-sm">
            B
          </span>
          <span>Byte4Bite</span>
        </Link>

        <div className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-600">
          <Link href="/" className="transition hover:text-emerald-600">
            Home
          </Link>
          <Link href="/dashboard" className="transition hover:text-emerald-600">
            Dashboard
          </Link>
          <a href="#how-it-works" className="transition hover:text-emerald-600">
            How it works
          </a>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;