"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { authFetch, clearSession, getUser } from "@/services/auth";

interface Profile {
  user_id: number;
  email: string;
  dietary_restriction?: string;
  allergies?: string[];
  health_goals?: string[];
}

export default function ProfilePage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [dietaryRestriction, setDietaryRestriction] = useState("");
  const [allergies, setAllergies] = useState("");
  const [healthGoals, setHealthGoals] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getUser()) {
      router.replace("/signin");
      return;
    }
    authFetch("/api/auth/profile")
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) {
          setError(data.detail || "Failed to load profile");
          return;
        }
        const p = data.profile as Profile;
        setProfile(p);
        setDietaryRestriction(p.dietary_restriction || "");
        setAllergies((p.allergies || []).join(", "));
        setHealthGoals((p.health_goals || []).join(", "));
      })
      .catch(() => setError("Could not load profile"));
  }, [router]);

  const handleSave = async () => {
    setStatus("Saving…");
    const res = await authFetch("/api/auth/profile", {
      method: "PUT",
      body: JSON.stringify({
        dietary_restriction: dietaryRestriction || null,
        allergies: allergies.split(",").map((s) => s.trim()).filter(Boolean),
        health_goals: healthGoals.split(",").map((s) => s.trim()).filter(Boolean),
      }),
    });
    const data = await res.json();
    setStatus(data.success ? "Profile updated." : data.detail || "Update failed");
  };

  const handleLogout = () => {
    clearSession();
    router.push("/signin");
  };

  if (!profile && !error) {
    return <p className="p-8 text-slate-600">Loading profile…</p>;
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <h1 className="text-3xl font-bold text-slate-900">Your profile</h1>
      {profile && <p className="mt-2 text-slate-600">{profile.email}</p>}
      {error && <p className="mt-4 text-red-600">{error}</p>}

      <div className="mt-8 space-y-4">
        <label className="block text-sm font-semibold">Dietary restriction</label>
        <select
          value={dietaryRestriction}
          onChange={(e) => setDietaryRestriction(e.target.value)}
          className="w-full rounded-2xl border border-slate-200 px-4 py-3"
        >
          <option value="">None</option>
          <option value="vegetarian">Vegetarian</option>
          <option value="vegan">Vegan</option>
          <option value="halal">Halal</option>
          <option value="gluten-free">Gluten-free</option>
        </select>

        <label className="block text-sm font-semibold">Allergies (comma-separated)</label>
        <input
          value={allergies}
          onChange={(e) => setAllergies(e.target.value)}
          className="w-full rounded-2xl border border-slate-200 px-4 py-3"
          placeholder="peanuts, shellfish"
        />

        <label className="block text-sm font-semibold">Health goals (comma-separated)</label>
        <input
          value={healthGoals}
          onChange={(e) => setHealthGoals(e.target.value)}
          className="w-full rounded-2xl border border-slate-200 px-4 py-3"
          placeholder="weight_loss, high_protein"
        />

        <button
          type="button"
          onClick={handleSave}
          className="w-full rounded-2xl bg-emerald-600 py-3 font-semibold text-white hover:bg-emerald-700"
        >
          Save profile
        </button>
        {status && <p className="text-sm text-emerald-700">{status}</p>}
      </div>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/saved" className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold hover:bg-slate-50">
          Saved recipes
        </Link>
        <Link href="/dashboard" className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold hover:bg-slate-50">
          Dashboard
        </Link>
        <button type="button" onClick={handleLogout} className="rounded-2xl border border-red-200 px-4 py-2 text-sm font-semibold text-red-600">
          Sign out
        </button>
      </div>
    </div>
  );
}
