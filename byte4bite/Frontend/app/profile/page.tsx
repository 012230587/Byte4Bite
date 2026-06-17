"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/contexts/AuthContext";
import { fetchProfile, parseApiError, updateProfile } from "@/services/auth";

interface Profile {
  user_id: number;
  email: string;
  dietary_restriction?: string;
  allergies?: string[];
  health_goals?: string[];
}

export default function ProfilePage() {
  const { user, logout, loading: authLoading } = useRequireAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [dietaryRestriction, setDietaryRestriction] = useState("");
  const [allergies, setAllergies] = useState("");
  const [healthGoals, setHealthGoals] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading || !user) return;
    fetchProfile()
      .then((data) => {
        if (!data?.success) {
          setError(parseApiError(data, "Failed to load profile"));
          return;
        }
        const p = data.profile as unknown as Profile;
        setProfile(p);
        setDietaryRestriction(p.dietary_restriction || "");
        setAllergies((p.allergies || []).join(", "));
        setHealthGoals((p.health_goals || []).join(", "));
      })
      .catch(() => setError("Could not load profile"))
      .finally(() => setLoading(false));
  }, [authLoading, user]);

  const handleSave = async () => {
    setStatus("Saving…");
    const { ok, data } = await updateProfile({
      dietary_restriction: dietaryRestriction || null,
      allergies: allergies.split(",").map((s) => s.trim()).filter(Boolean),
      health_goals: healthGoals.split(",").map((s) => s.trim()).filter(Boolean),
    });
    setStatus(
      ok && data.success
        ? "Profile updated — dashboard filters will use these preferences."
        : parseApiError(data, "Update failed")
    );
  };

  if (authLoading || loading) {
    return <p className="p-8 text-[#6b635a]">Loading profile…</p>;
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-12">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#c94c4c]">Your account</p>
      <h1 className="font-brand mt-3 text-4xl font-bold text-[#2d2d2d]">Profile</h1>
      {profile && <p className="mt-2 text-[#6b635a]">{profile.email}</p>}
      {error ? <p className="mt-4 text-red-700">{error}</p> : null}

      <div className="rt-panel mt-8 space-y-4 rounded-2xl p-6">
        <label className="block text-sm font-semibold text-[#2d2d2d]">Default dietary restriction</label>
        <select
          value={dietaryRestriction}
          onChange={(e) => setDietaryRestriction(e.target.value)}
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3"
        >
          <option value="">None</option>
          <option value="vegetarian">Vegetarian</option>
          <option value="vegan">Vegan</option>
          <option value="halal">Halal</option>
          <option value="gluten-free">Gluten-free</option>
        </select>

        <label className="block text-sm font-semibold text-[#2d2d2d]">Allergies (comma-separated)</label>
        <input
          value={allergies}
          onChange={(e) => setAllergies(e.target.value)}
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3"
          placeholder="peanuts, shellfish"
        />

        <label className="block text-sm font-semibold text-[#2d2d2d]">Health goals (comma-separated)</label>
        <input
          value={healthGoals}
          onChange={(e) => setHealthGoals(e.target.value)}
          className="w-full rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3"
          placeholder="high_protein, low_calorie"
        />

        <button
          type="button"
          onClick={handleSave}
          className="rt-btn-primary w-full rounded-xl py-3 font-semibold"
        >
          Save profile
        </button>
        {status ? <p className="text-sm text-[#6b635a]">{status}</p> : null}
      </div>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/saved"
          className="rounded-xl border border-[#e8dfd4] bg-white px-4 py-2 text-sm font-semibold hover:border-[#c94c4c] hover:text-[#c94c4c]"
        >
          Saved recipes
        </Link>
        <Link
          href="/dashboard"
          className="rounded-xl border border-[#e8dfd4] bg-white px-4 py-2 text-sm font-semibold hover:border-[#c94c4c] hover:text-[#c94c4c]"
        >
          Dashboard
        </Link>
        <button
          type="button"
          onClick={() => {
            logout();
            window.location.href = "/signin";
          }}
          className="rounded-xl border border-red-200 px-4 py-2 text-sm font-semibold text-red-700"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
