"use client";
import { useCallback, useEffect, useState } from "react";
import RecipeCard from "@/components/RecipeCard";
import RecipeDetail from "@/components/RecipeDetail";
import Loader from "@/components/Loader";

interface Recipe {
  title: string;
  description: string;
  ingredients: string[];
  instructions: string[];
  prep_time: string;
  difficulty: string;
  dietary_tags?: string[];
  is_generated?: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function Dashboard() {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchIngredients, setSearchIngredients] = useState("");
  const [dietaryRestriction, setDietaryRestriction] = useState("");
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string>("");
  const [hasSearched, setHasSearched] = useState(false);
  const [lastSearchQuery, setLastSearchQuery] = useState("");

  const fetchRecipes = useCallback(async (ingredientsQuery: string = "") => {
    setLoading(true);
    setError(null);
    try {
      const queryParams = new URLSearchParams();
      if (ingredientsQuery) queryParams.set("ingredients", ingredientsQuery);
      if (dietaryRestriction) queryParams.set("restriction", dietaryRestriction);
      const query = queryParams.toString() ? `?${queryParams.toString()}` : "";
      const res = await fetch(`${API_BASE}/api/recipes${query}`);
      if (!res.ok) throw new Error(`Server responded with ${res.status}`);
      const data = await res.json();
      const list = Array.isArray(data) ? data : [];
      setRecipes(list);
      if (list.length > 0 && (!selectedRecipe || selectedRecipe.title !== list[0].title)) {
        setSelectedRecipe(list[0]);
      }
    } catch (err) {
      console.error("Connection error:", err);
      setError("Failed to connect to the recipe server. Please ensure the backend is running at http://127.0.0.1:8000");
    } finally {
      setLoading(false);
    }
  }, [dietaryRestriction, selectedRecipe]);

  useEffect(() => {
    fetchRecipes();
  }, [fetchRecipes]);

  const handleSearch = async () => {
    const query = searchIngredients.trim();
    setSearching(true);
    setHasSearched(true);
    setLastSearchQuery(query);
    await fetchRecipes(query);
    setSearching(false);
  };

  const handleGenerateRecipe = async () => {
    const query = lastSearchQuery || searchIngredients.trim();
    if (!query) {
      window.alert("Please enter ingredients first.");
      return;
    }

    setIsGenerating(true);
    setSaveStatus("");

    try {
      const response = await fetch(`${API_BASE}/api/recipes/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, restriction: dietaryRestriction }),
      });
      const data = await response.json();
      if (data.recipes && data.recipes.length > 0) {
        setSelectedRecipe(data.recipes[0]);
        setLastSearchQuery(query);
        setHasSearched(true);
      }
    } catch (err) {
      console.error("Generation error:", err);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveGeneratedRecipe = async () => {
    if (!selectedRecipe) return;

    setSaveStatus("Saving recipe to memory...");
    try {
      const response = await fetch(`${API_BASE}/api/recipes/memory/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipe: selectedRecipe, query: lastSearchQuery }),
      });
      const data = await response.json();
      setSaveStatus(data.success ? "Recipe saved successfully." : `Save failed: ${data.error || "unknown error"}`);
    } catch (err) {
      console.error("Save error:", err);
      setSaveStatus("Unable to save recipe. Please try again later.");
    }
  };

  const handleRecipeSelect = (recipe: Recipe) => {
    setSelectedRecipe(recipe);
    setSaveStatus("");
  };

  return (
    <div className="min-h-screen bg-slate-50 py-10">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <header className="mb-10 rounded-[2rem] bg-white/90 p-8 shadow-sm shadow-slate-200 border border-slate-200">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-emerald-600">Smart cooking</p>
              <h1 className="mt-3 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
                Find recipes fast, or generate one from whatever is in your pantry.
              </h1>
              <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
                Search your dataset, preview matches, and use AI to create recipe instructions with a polished interface.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-3xl bg-slate-50 p-5 text-center shadow-sm">
                <p className="text-3xl font-bold text-slate-900">{recipes.length}</p>
                <p className="mt-2 text-sm text-slate-500">Available recipes</p>
              </div>
              <div className="rounded-3xl bg-slate-50 p-5 text-center shadow-sm">
                <p className="text-3xl font-bold text-slate-900">{selectedRecipe?.is_generated ? "AI" : "Classic"}</p>
                <p className="mt-2 text-sm text-slate-500">Selected recipe type</p>
              </div>
            </div>
          </div>
        </header>

        {error && (
          <div className="mb-8 rounded-2xl bg-red-50 p-6 text-red-700 border border-red-200 shadow-sm">
            <p className="font-semibold flex items-center gap-2">⚠️ Connection Issue</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        <div className="rounded-[2rem] bg-white p-8 shadow-sm border border-slate-200 mb-8">
          <label htmlFor="ingredient-search" className="block text-sm font-semibold text-slate-700 mb-2">
            Enter ingredients or a recipe name
          </label>
          <div className="flex flex-col gap-4 md:flex-row md:items-end">
            <div className="flex-1 flex flex-col gap-3">
            <input
              id="ingredient-search"
              value={searchIngredients}
              onChange={(e) => setSearchIngredients(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 shadow-sm focus:border-emerald-500 focus:ring-emerald-200 focus:outline-none text-black"
              placeholder="e.g. chicken, garlic, coconut milk"
            />
            <label htmlFor="dietary-restriction" className="block text-sm font-semibold text-slate-700">
              Dietary restriction (optional)
            </label>
            <select
              id="dietary-restriction"
              value={dietaryRestriction}
              onChange={(e) => setDietaryRestriction(e.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm focus:border-emerald-500 focus:ring-emerald-200 focus:outline-none"
            >
              <option value="">No restriction</option>
              <option value="vegetarian">Vegetarian</option>
              <option value="vegan">Vegan</option>
              <option value="halal">Halal</option>
              <option value="gluten-free">Gluten-free</option>
            </select>
          </div>
          <button
            onClick={handleSearch}
            disabled={searching}
            className="rounded-2xl bg-emerald-600 px-5 py-3 text-white font-semibold hover:bg-emerald-700 disabled:bg-slate-300"
          >
            {searching ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-4">
          <Loader label="Loading recipes" />
          <Loader label="Refreshing suggestions" />
        </div>
      ) : recipes.length > 0 ? (
        <div className="grid gap-4">
          {recipes.map((recipe, index) => (
            <div key={`${recipe.title}-${index}`} className="space-y-4">
              <RecipeCard
                recipe={recipe}
                selected={selectedRecipe?.title === recipe.title}
                onClick={() => handleRecipeSelect(recipe)}
              />
              {selectedRecipe?.title === recipe.title ? (
                <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-sm shadow-slate-200">
                  <RecipeDetail recipe={selectedRecipe} statusMessage={saveStatus || undefined} />
                  {selectedRecipe.is_generated ? (
                    <div className="mt-6 grid gap-4">
                      <button
                        type="button"
                        onClick={handleSaveGeneratedRecipe}
                        className="w-full rounded-3xl bg-emerald-600 px-6 py-4 text-sm font-semibold text-white transition hover:bg-emerald-700"
                      >
                        Save recipe to memory
                      </button>
                      <button
                        type="button"
                        onClick={handleGenerateRecipe}
                        disabled={isGenerating}
                        className="w-full rounded-3xl bg-slate-900 px-6 py-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"
                      >
                        {isGenerating ? "Generating..." : "Generate another recipe"}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : hasSearched ? (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-slate-600">
          No recipes matched your ingredients yet. Generate a custom recipe to continue.
        </div>
      ) : (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-slate-600">
          Start by searching ingredients or generating a recipe to see suggestions here.
        </div>
      )}

    </div>
  </div>
  );
}