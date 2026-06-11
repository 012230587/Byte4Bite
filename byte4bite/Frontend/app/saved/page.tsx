"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import RecipeCard from "@/components/RecipeCard";
import { useRequireAuth } from "@/contexts/AuthContext";
import { fetchSavedRecipes, parseApiError } from "@/services/auth";

interface Recipe {
  title: string;
  description: string;
  ingredients: string[];
  instructions: string[];
  prep_time: string;
  difficulty: string;
  saved_at?: string;
  notes?: string;
}

export default function SavedRecipesPage() {
  const { loading: authLoading } = useRequireAuth();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    fetchSavedRecipes()
      .then((data) => {
        if (!data.success) {
          setError(parseApiError(data, "Failed to load saved recipes"));
          return;
        }
        setRecipes((data.recipes || []) as Recipe[]);
      })
      .catch(() => setError("Could not load saved recipes"))
      .finally(() => setLoading(false));
  }, [authLoading]);

  if (authLoading) {
    return <p className="p-8 text-[#6b635a]">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#c94c4c]">Your cookbook</p>
      <h1 className="font-brand mt-3 text-4xl font-bold text-[#2d2d2d]">Saved recipes</h1>
      <p className="mt-2 text-[#6b635a]">Recipes you saved from the dashboard.</p>

      <div className="mt-6 flex gap-3">
        <Link href="/dashboard" className="text-sm font-semibold text-[#c94c4c] hover:underline">
          ← Back to dashboard
        </Link>
        <Link href="/profile" className="text-sm font-semibold text-[#c94c4c] hover:underline">
          Profile
        </Link>
      </div>

      {loading && <p className="mt-8 text-[#6b635a]">Loading…</p>}
      {error && <p className="mt-8 text-red-700">{error}</p>}
      {!loading && !error && recipes.length === 0 && (
        <p className="mt-8 rt-panel rounded-2xl border border-dashed border-[#e8dfd4] p-8 text-center text-[#6b635a]">
          No saved recipes yet. Get a recipe on the dashboard and click Save.
        </p>
      )}

      <div className="mt-8 grid gap-4">
        {recipes.map((recipe, i) => (
          <div key={`${recipe.title}-${i}`}>
            <RecipeCard recipe={recipe} />
            {recipe.saved_at ? (
              <p className="mt-2 text-xs text-[#a89f94]">Saved {recipe.saved_at}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
