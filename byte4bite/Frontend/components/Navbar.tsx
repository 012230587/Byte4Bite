"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { clearSession, getUser } from "@/services/auth";

const Navbar = () => {
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    setEmail(getUser()?.email ?? null);
  }, []);

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/95 backdrop-blur-xl shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-3 text-lg font-semibold text-slate-900">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-sm">
            B
          </span>
          <span>Byte4Bite</span>
        </Link>

        <div className="hidden md:flex items-center gap-4 text-sm font-medium text-slate-600">
          <Link href="/" className="transition hover:text-emerald-600">
            Home
          </Link>
          <Link href="/dashboard" className="transition hover:text-emerald-600">
            Dashboard
          </Link>
          {email ? (
            <>
              <Link href="/profile" className="transition hover:text-emerald-600">
                Profile
              </Link>
              <Link href="/saved" className="transition hover:text-emerald-600">
                Saved
              </Link>
              <button
                type="button"
                onClick={() => {
                  clearSession();
                  setEmail(null);
                  window.location.href = "/signin";
                }}
                className="rounded-full border border-slate-300 px-4 py-2 text-slate-600 transition hover:bg-slate-50"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/register" className="rounded-full border border-emerald-600 px-4 py-2 text-emerald-600 transition hover:bg-emerald-50">
                Register
              </Link>
              <Link href="/signin" className="rounded-full bg-emerald-600 px-4 py-2 text-white transition hover:bg-emerald-700">
                Sign in
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
