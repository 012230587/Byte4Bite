"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";

function SignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, isAuthenticated, loading: authLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const nextPath = searchParams.get("next") || "/dashboard";

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      router.replace(nextPath);
    }
  }, [authLoading, isAuthenticated, router, nextPath]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const result = await login(email, password);
    if (!result.success) {
      setError(result.error || "Login failed");
      setLoading(false);
      return;
    }
    router.push(nextPath);
  };

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#c94c4c]">Welcome back</p>
      <h1 className="font-brand mt-3 text-4xl font-bold text-[#2d2d2d]">Sign in</h1>
      <p className="mt-2 text-[#6b635a]">Save recipes and sync your dietary preferences.</p>

      <form onSubmit={handleSubmit} className="rt-panel mt-8 space-y-4 rounded-2xl p-6">
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3 focus:border-[#c94c4c] focus:outline-none focus:ring-2 focus:ring-[#c94c4c]/20"
        />
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3 focus:border-[#c94c4c] focus:outline-none focus:ring-2 focus:ring-[#c94c4c]/20"
        />
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="rt-btn-primary w-full rounded-xl py-3 font-semibold disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-[#6b635a]">
        No account?{" "}
        <Link href={`/register${nextPath !== "/dashboard" ? `?next=${encodeURIComponent(nextPath)}` : ""}`} className="font-semibold text-[#c94c4c] hover:underline">
          Register
        </Link>
      </p>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={<p className="p-8 text-[#6b635a]">Loading…</p>}>
      <SignInForm />
    </Suspense>
  );
}
