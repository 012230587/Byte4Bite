"use client";

import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";

const Navbar = () => {
  const { user, loading, logout, isAuthenticated } = useAuth();

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-[#e8dfd4] bg-[#faf7f2]/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <Link href="/" className="font-brand text-2xl font-bold tracking-tight text-[#2d2d2d]">
          Byte4Bite
        </Link>
        <p className="hidden sm:block text-xs uppercase tracking-[0.28em] text-[#6b635a]">
          Fast prep, big flavours
        </p>

        <div className="flex items-center gap-3 text-sm font-medium text-[#6b635a]">
          <Link href="/dashboard" className="hidden md:inline transition hover:text-[#c94c4c]">
            Get recipe
          </Link>
          {!loading && isAuthenticated && user ? (
            <>
              <span className="hidden lg:inline max-w-[160px] truncate text-xs text-[#a89f94]">
                {user.email}
              </span>
              <Link href="/saved" className="transition hover:text-[#c94c4c]">
                Saved
              </Link>
              <Link href="/profile" className="hidden sm:inline transition hover:text-[#c94c4c]">
                Profile
              </Link>
              <button
                type="button"
                onClick={logout}
                className="rounded-full border border-[#e8dfd4] px-3 py-1.5 transition hover:border-[#c94c4c] hover:text-[#c94c4c]"
              >
                Sign out
              </button>
            </>
          ) : !loading ? (
            <>
              <Link href="/register" className="hidden sm:inline transition hover:text-[#c94c4c]">
                Register
              </Link>
              <Link
                href="/signin"
                className="rounded-full bg-[#c94c4c] px-4 py-2 text-white transition hover:bg-[#b03f3f]"
              >
                Sign in
              </Link>
            </>
          ) : null}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
