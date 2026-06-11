"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import RecipeCard from "@/components/RecipeCard";
import { authFetch, getUser } from "@/services/auth";

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
  const router = useRouter();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getUser()) {
      router.replace("/signin");
      return;
    }
    authFetch("/api/auth/saved-recipes")
      .then((r) => r.json())
      .then((data) => {
        if (!data.success) {
          setError(data.detail || "Failed to load saved recipes");
          return;
        }
        setRecipes(data.recipes || []);
      })
      .catch(() => setError("Could not load saved recipes"))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-3xl font-bold text-slate-900">Saved recipes</h1>
      <p className="mt-2 text-slate-600">Recipes you bookmarked from the dashboard.</p>

      <div className="mt-6 flex gap-3">
        <Link href="/dashboard" className="text-sm font-semibold text-emerald-600 hover:underline">
          ← Back to dashboard
        </Link>
        <Link href="/profile" className="text-sm font-semibold text-emerald-600 hover:underline">
          Profile
        </Link>
      </div>

      {loading && <p className="mt-8 text-slate-500">Loading…</p>}
      {error && <p className="mt-8 text-red-600">{error}</p>}
      {!loading && !error && recipes.length === 0 && (
        <p className="mt-8 rounded-2xl border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No saved recipes yet. Generate one on the dashboard and click Save.
        </p>
      )}

      <div className="mt-8 grid gap-4">
        {recipes.map((recipe, i) => (
          <div key={`${recipe.title}-${i}`}>
            <RecipeCard recipe={recipe} />
            {recipe.saved_at && (
              <p className="mt-2 text-xs text-slate-400">Saved {recipe.saved_at}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
