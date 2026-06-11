"use client";
import { useCallback, useEffect, useState } from "react";
import RecipeCard from "@/components/RecipeCard";
import RecipeDetail from "@/components/RecipeDetail";
import Loader from "@/components/Loader";
import { authFetch, getUser } from "@/services/auth";

interface Recipe {
  title: string;
  description: string;
  ingredients: string[];
  instructions: string[];
  prep_time: string;
  difficulty: string;
  dietary_tags?: string[];
  cuisine?: string;
  is_generated?: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const CUISINE_OPTIONS = [
  { value: "", label: "Any cuisine" },
  { value: "indian", label: "Indian" },
  { value: "italian", label: "Italian" },
  { value: "mexican", label: "Mexican" },
  { value: "chinese", label: "Chinese" },
  { value: "japanese", label: "Japanese" },
  { value: "thai", label: "Thai" },
  { value: "mediterranean", label: "Mediterranean" },
  { value: "korean", label: "Korean" },
  { value: "middle eastern", label: "Middle Eastern" },
  { value: "american", label: "American" },
  { value: "french", label: "French" },
  { value: "pakistani", label: "Pakistani" },
  { value: "fusion", label: "Fusion" },
];

export default function Dashboard() {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchIngredients, setSearchIngredients] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [dietaryRestrictions, setDietaryRestrictions] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string>("");
  const [hasSearched, setHasSearched] = useState(false);
  const [lastSearchQuery, setLastSearchQuery] = useState("");

  const dietaryOptions = [
    { value: "vegetarian", label: "Vegetarian" },
    { value: "vegan", label: "Vegan" },
    { value: "halal", label: "Halal" },
    { value: "gluten-free", label: "Gluten-free" },
  ];

  const toggleRestriction = (value: string) => {
    setDietaryRestrictions((prev) =>
      prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]
    );
  };

  const fetchRecipes = useCallback(async (ingredientsQuery: string = "") => {
    setLoading(true);
    setError(null);
    try {
      const queryParams = new URLSearchParams();
      if (ingredientsQuery) queryParams.set("ingredients", ingredientsQuery);
      dietaryRestrictions.forEach((restriction) => queryParams.append("restrictions", restriction));
      const query = queryParams.toString() ? `?${queryParams.toString()}` : "";
      const res = await fetch(`${API_BASE}/api/recipes${query}`);
      if (!res.ok) throw new Error(`Server responded with ${res.status}`);
      const data = await res.json();
      const list = Array.isArray(data) ? data.slice(0, 20) : [];
      setRecipes(list);
      if (list.length > 0) {
        setSelectedRecipe(list[0]);
        setSelectedIndex(0);
      } else {
        setSelectedRecipe(null);
        setSelectedIndex(null);
      }
    } catch (err) {
      console.error("Connection error:", err);
      setError("Failed to connect to the recipe server. Please ensure the backend is running at http://127.0.0.1:8000");
    } finally {
      setLoading(false);
    }
  }, [dietaryRestrictions]);

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
    const query = searchIngredients.trim() || lastSearchQuery;
    if (!query) {
      setGenerateError("Enter your ingredients (comma-separated) before generating.");
      return;
    }

    setIsGenerating(true);
    setGenerateError(null);
    setSaveStatus("");

    try {
      const response = await fetch(`${API_BASE}/api/recipes/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          restrictions: dietaryRestrictions,
          cuisine: cuisine || undefined,
        }),
      });
      const data = await response.json();
      if (data.error && (!data.recipes || data.recipes.length === 0)) {
        setGenerateError(data.error);
        return;
      }
      if (data.recipes && data.recipes.length > 0) {
        const generated = data.recipes[0] as Recipe;
        setRecipes([generated]);
        setSelectedRecipe(generated);
        setSelectedIndex(0);
        setLastSearchQuery(query);
        setHasSearched(true);
      }
    } catch (err) {
      console.error("Generation error:", err);
      setGenerateError("Could not generate a recipe. Check that the backend is running and GEMINI_API_KEY is set.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveRecipe = async () => {
    if (!selectedRecipe) return;

    const user = getUser();
    if (!user) {
      setSaveStatus("Please sign in to save recipes to your account.");
      return;
    }

    setSaveStatus("Saving recipe...");
    try {
      const response = await authFetch("/api/auth/saved-recipes", {
        method: "POST",
        body: JSON.stringify({ recipe: selectedRecipe, notes: lastSearchQuery }),
      });
      const data = await response.json();
      setSaveStatus(
        data.success
          ? "Recipe saved to your account. View it under Saved recipes."
          : `Save failed: ${data.detail || data.error || "unknown error"}`
      );
    } catch (err) {
      console.error("Save error:", err);
      setSaveStatus("Unable to save recipe. Please try again later.");
    }
  };

  const handleRecipeSelect = (recipe: Recipe, index: number) => {
    setSelectedRecipe(recipe);
    setSelectedIndex(index);
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
                Generate complete recipes from your pantry
              </h1>
              <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
                Add ingredients, pick a cuisine and dietary needs, then generate a full recipe with unique name,
                measured ingredients, and step-by-step instructions from prep through serving.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-3xl bg-slate-50 p-5 text-center shadow-sm">
                <p className="text-3xl font-bold text-slate-900">{recipes.length}</p>
                <p className="mt-2 text-sm text-slate-500">Shown recipes</p>
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
            <p className="font-semibold flex items-center gap-2">Connection issue</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}

        <div className="rounded-[2rem] bg-black p-8 shadow-lg border-2 border-black mb-8 text-white">
          <div className="mb-6 space-y-3">
            <p className="text-sm uppercase tracking-[0.32em] text-slate-400">Recipe builder</p>
            <h2 className="text-2xl font-bold tracking-tight text-white">Ingredients, cuisine & dietary filters</h2>
            <p className="text-sm leading-6 text-slate-300 max-w-2xl">
              List what you have (comma-separated). Choose a cuisine for authentic flavor. Generate creates one
              complete original recipe — not a copy from the dataset.
            </p>
          </div>

          <div className="flex flex-col gap-4">
            <label htmlFor="ingredient-search" className="block text-sm font-semibold text-white">
              Pantry ingredients
            </label>
            <input
              id="ingredient-search"
              value={searchIngredients}
              onChange={(e) => setSearchIngredients(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleGenerateRecipe();
              }}
              className="w-full rounded-2xl border border-white/15 bg-slate-950 px-4 py-3 text-white shadow-inner shadow-black/20 focus:border-white focus:ring-2 focus:ring-white/20 focus:outline-none placeholder:text-slate-500"
              placeholder="e.g. chicken, garlic, coconut milk, spinach"
            />

            <label htmlFor="cuisine-select" className="block text-sm font-semibold text-white">
              Cuisine style
            </label>
            <select
              id="cuisine-select"
              value={cuisine}
              onChange={(e) => setCuisine(e.target.value)}
              className="w-full rounded-2xl border border-white/15 bg-slate-950 px-4 py-3 text-white focus:border-white focus:ring-2 focus:ring-white/20 focus:outline-none"
            >
              {CUISINE_OPTIONS.map((opt) => (
                <option key={opt.value || "any"} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <p className="text-sm font-semibold text-white">Dietary restrictions (optional)</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {dietaryOptions.map((option) => (
                <label
                  key={option.value}
                  className="inline-flex cursor-pointer items-center gap-3 rounded-2xl border border-white/15 bg-slate-900 px-4 py-3 text-sm text-white shadow-sm transition hover:border-white/30"
                >
                  <input
                    type="checkbox"
                    checked={dietaryRestrictions.includes(option.value)}
                    onChange={() => toggleRestriction(option.value)}
                    className="h-4 w-4 rounded border-white/30 bg-slate-950 text-emerald-500 focus:ring-emerald-400"
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>

            {generateError && (
              <p className="text-sm text-red-300">{generateError}</p>
            )}

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <button
                type="button"
                onClick={handleGenerateRecipe}
                disabled={isGenerating}
                className="rounded-2xl bg-emerald-500 px-6 py-3 font-semibold text-black transition hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-400"
              >
                {isGenerating ? "Generating recipe…" : "Generate complete recipe"}
              </button>
              <button
                type="button"
                onClick={handleSearch}
                disabled={searching}
                className="rounded-2xl bg-white px-6 py-3 font-semibold text-black transition hover:bg-slate-200 disabled:bg-slate-700 disabled:text-slate-300"
              >
                {searching ? "Searching…" : "Search dataset"}
              </button>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="grid gap-4">
            <Loader label="Loading recipes" />
          </div>
        ) : recipes.length > 0 ? (
          <div className="grid gap-4">
            {recipes.map((recipe, index) => (
              <div key={`${recipe.title}-${index}`} className="space-y-4">
                <RecipeCard
                  recipe={recipe}
                  selected={selectedIndex === index}
                  onClick={() => handleRecipeSelect(recipe, index)}
                />
                {selectedIndex === index && selectedRecipe ? (
                  <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-sm shadow-slate-200">
                    <RecipeDetail recipe={selectedRecipe} statusMessage={saveStatus || undefined} />
                    <div className="mt-6 grid gap-4">
                      <button
                        type="button"
                        onClick={handleSaveRecipe}
                        className="w-full rounded-3xl bg-emerald-600 px-6 py-4 text-sm font-semibold text-white transition hover:bg-emerald-700"
                      >
                        Save recipe
                      </button>
                      {selectedRecipe.is_generated ? (
                        <button
                          type="button"
                          onClick={handleGenerateRecipe}
                          disabled={isGenerating}
                          className="w-full rounded-3xl bg-slate-900 px-6 py-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"
                        >
                          {isGenerating ? "Generating…" : "Generate another variation"}
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : hasSearched ? (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <p className="text-slate-600">No dataset matches. Use Generate complete recipe to create one from your pantry.</p>
            <button
              type="button"
              onClick={handleGenerateRecipe}
              disabled={isGenerating}
              className="mt-6 rounded-2xl bg-emerald-600 px-6 py-3 font-semibold text-white hover:bg-emerald-700 disabled:bg-slate-300"
            >
              {isGenerating ? "Generating…" : "Generate complete recipe"}
            </button>
          </div>
        ) : (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-slate-600">
            Enter ingredients above, select cuisine, then click Generate — or Search dataset for existing matches.
          </div>
        )}
      </div>
    </div>
  );
}
