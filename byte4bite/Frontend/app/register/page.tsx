"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { register, isAuthenticated, loading: authLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
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
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    setError("");
    const result = await register(email, password);
    if (!result.success) {
      setError(result.error || "Registration failed");
      setLoading(false);
      return;
    }
    router.push(nextPath);
  };

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#c94c4c]">Join Byte4Bite</p>
      <h1 className="font-brand mt-3 text-4xl font-bold text-[#2d2d2d]">Create account</h1>
      <p className="mt-2 text-[#6b635a]">Free account — save recipes and keep your preferences.</p>

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
          minLength={6}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password (min 6 characters)"
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3 focus:border-[#c94c4c] focus:outline-none focus:ring-2 focus:ring-[#c94c4c]/20"
        />
        <input
          type="password"
          required
          minLength={6}
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Confirm password"
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3 focus:border-[#c94c4c] focus:outline-none focus:ring-2 focus:ring-[#c94c4c]/20"
        />
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="rt-btn-primary w-full rounded-xl py-3 font-semibold disabled:opacity-50"
        >
          {loading ? "Creating account…" : "Register"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-[#6b635a]">
        Already have an account?{" "}
        <Link href={`/signin${nextPath !== "/dashboard" ? `?next=${encodeURIComponent(nextPath)}` : ""}`} className="font-semibold text-[#c94c4c] hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<p className="p-8 text-[#6b635a]">Loading…</p>}>
      <RegisterForm />
    </Suspense>
  );
}
