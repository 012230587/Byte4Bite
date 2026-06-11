"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import RecipeDetail from "@/components/RecipeDetail";
import Loader from "@/components/Loader";
import { useAuth } from "@/contexts/AuthContext";
import {
  parseApiError,
  recipeFetch,
  saveRecipeToAccount,
} from "@/services/auth";

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
  inspired_by?: string[];
  retrieval_note?: string;
}


const CUISINE_GROUPS = [
  {
    label: "Popular",
    options: [
      { value: "", label: "Any cuisine" },
      { value: "italian", label: "Italian" },
      { value: "indian", label: "Indian" },
      { value: "thai", label: "Thai" },
      { value: "mexican", label: "Mexican" },
      { value: "chinese", label: "Chinese" },
      { value: "japanese", label: "Japanese" },
      { value: "korean", label: "Korean" },
    ],
  },
  {
    label: "More styles",
    options: [
      { value: "mediterranean", label: "Mediterranean" },
      { value: "middle eastern", label: "Middle Eastern" },
      { value: "french", label: "French" },
      { value: "american", label: "American" },
      { value: "greek", label: "Greek" },
      { value: "vietnamese", label: "Vietnamese" },
      { value: "spanish", label: "Spanish" },
      { value: "pakistani", label: "Pakistani" },
      { value: "filipino", label: "Filipino" },
      { value: "asian", label: "Asian" },
      { value: "fusion", label: "Fusion" },
    ],
  },
];

const ALL_CUISINES = CUISINE_GROUPS.flatMap((group) => group.options);

const DIETARY_OPTIONS = [
  { value: "vegetarian", label: "Vegetarian" },
  { value: "vegan", label: "Vegan" },
  { value: "halal", label: "Halal" },
  { value: "gluten-free", label: "Gluten-free" },
];

export default function Dashboard() {
  const { user, isAuthenticated, loading: authLoading, profile } = useAuth();
  const prefsApplied = useRef(false);
  const [pantryInput, setPantryInput] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [dietaryRestrictions, setDietaryRestrictions] = useState<string[]>([]);
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState("");
  const [botMessage, setBotMessage] = useState("");
  const [lastQuery, setLastQuery] = useState("");

  useEffect(() => {
    if (authLoading || prefsApplied.current || !profile) return;
    const restriction = profile.dietary_restriction;
    if (restriction && ["vegetarian", "vegan", "halal", "gluten-free"].includes(restriction)) {
      setDietaryRestrictions((prev) =>
        prev.includes(restriction) ? prev : [...prev, restriction]
      );
    }
    prefsApplied.current = true;
  }, [authLoading, profile]);

  const toggleRestriction = (value: string) => {
    setDietaryRestrictions((prev) =>
      prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]
    );
  };

  const handleGetRecipe = async () => {
    const query = pantryInput.trim();
    if (!query) {
      setError("Tell us what is in your pantry — e.g. chicken, rice, garlic, spinach.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setSaveStatus("");
    setRecipe(null);
    setBotMessage("Finding similar dishes in our corpus and composing your recipe…");
    setLastQuery(query);

    try {
      const response = await recipeFetch("/api/recipes/generate", {
        method: "POST",
        body: JSON.stringify({
          query,
          restrictions: dietaryRestrictions,
          cuisine: cuisine || undefined,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server responded with ${response.status}`);
      }

      const data = await response.json();

      if (data.error && (!data.recipes || data.recipes.length === 0)) {
        setError(data.error);
        setBotMessage("");
        return;
      }

      if (data.recipes?.length > 0) {
        const generated = {
          ...data.recipes[0],
          inspired_by: data.inspired_by || data.recipes[0].inspired_by,
          retrieval_note: data.retrieval_note || data.recipes[0].retrieval_note,
        } as Recipe;
        setRecipe(generated);
        setBotMessage(
          data.bot_message ||
            "Your tailored recipe is ready — inspired by the closest matches in our dataset."
        );
      }
    } catch (err) {
      console.error("Recipe error:", err);
      setError(
        "Could not get a recipe. Check that the backend is running and GEMINI_API_KEY is set in Backend/.env."
      );
      setBotMessage("");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveRecipe = async () => {
    if (!recipe) return;

    if (!isAuthenticated) {
      setSaveStatus("Sign in to save recipes.");
      return;
    }

    setSaveStatus("Saving…");
    try {
      const { ok, data } = await saveRecipeToAccount(recipe as Record<string, unknown>, lastQuery);
      setSaveStatus(
        ok && data.success
          ? "Saved to your account — view it under Saved recipes."
          : parseApiError(data, "Save failed")
      );
    } catch (err) {
      console.error("Save error:", err);
      setSaveStatus("Unable to save right now. Please try again.");
    }
  };

  const selectedCuisineLabel =
    ALL_CUISINES.find((opt) => opt.value === cuisine)?.label || "Any cuisine";

  return (
    <div className="min-h-screen bg-[#faf7f2] pb-16">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <header className="border-b border-[#e8dfd4] py-10 text-center sm:py-14">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-[#c94c4c]">
            What are you cooking tonight?
          </p>
          <h1 className="font-brand mt-4 text-4xl font-bold leading-tight text-[#2d2d2d] sm:text-5xl">
            Turn your pantry into dinner
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-[#6b635a] sm:text-lg">
            List what you have, pick a cuisine and dietary needs, then get one complete recipe —
            measured ingredients and clear steps from prep through serving.
          </p>
          {!authLoading && isAuthenticated && user ? (
            <p className="mt-4 text-sm text-[#6b635a]">
              Signed in as <span className="font-medium text-[#2d2d2d]">{user.email}</span>
              {profile?.dietary_restriction ? (
                <> · profile preference: {profile.dietary_restriction}</>
              ) : null}
            </p>
          ) : !authLoading ? (
            <p className="mt-4 text-sm text-[#6b635a]">
              <Link href="/signin?next=/dashboard" className="font-semibold text-[#c94c4c] hover:underline">
                Sign in
              </Link>{" "}
              to save recipes and sync dietary preferences.
            </p>
          ) : null}
        </header>

        <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:items-start">
          <section className="rt-panel rounded-2xl p-6 sm:p-8">
            <h2 className="font-brand text-2xl font-semibold text-[#2d2d2d]">Your pantry</h2>
            <p className="mt-2 text-sm leading-6 text-[#6b635a]">
              Comma-separated ingredients work best. We search 1,500+ corpus recipes semantically,
              then compose something new for you.
            </p>

            <label htmlFor="pantry-input" className="mt-6 block text-sm font-semibold text-[#2d2d2d]">
              Ingredients
            </label>
            <textarea
              id="pantry-input"
              rows={3}
              value={pantryInput}
              onChange={(e) => setPantryInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  handleGetRecipe();
                }
              }}
              placeholder="e.g. chicken thighs, coconut milk, spinach, garlic, rice"
              className="mt-2 w-full resize-y rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3 text-[#2d2d2d] placeholder:text-[#a89f94] focus:border-[#c94c4c] focus:outline-none focus:ring-2 focus:ring-[#c94c4c]/20"
            />

            <div className="mt-8">
              <p className="text-sm font-semibold text-[#2d2d2d]">Cuisine style</p>
              <p className="mt-1 text-xs text-[#6b635a]">
                Selected: <span className="font-medium text-[#c94c4c]">{selectedCuisineLabel}</span>
              </p>
              <div className="mt-3 space-y-4">
                {CUISINE_GROUPS.map((group) => (
                  <div key={group.label}>
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#a89f94]">
                      {group.label}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {group.options.map((opt) => (
                        <button
                          key={opt.value || "any"}
                          type="button"
                          onClick={() => setCuisine(opt.value)}
                          className={`rt-chip rounded-full px-3 py-1.5 text-sm ${
                            cuisine === opt.value ? "rt-chip-active" : ""
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8">
              <p className="text-sm font-semibold text-[#2d2d2d]">Dietary filters</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {DIETARY_OPTIONS.map((option) => {
                  const active = dietaryRestrictions.includes(option.value);
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => toggleRestriction(option.value)}
                      className={`rt-chip rounded-full px-3 py-1.5 text-sm ${
                        active ? "rt-chip-active" : ""
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {error ? (
              <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                {error}
              </div>
            ) : null}

            <button
              type="button"
              onClick={handleGetRecipe}
              disabled={isLoading}
              className="rt-btn-primary mt-8 w-full rounded-xl px-6 py-4 text-base font-semibold shadow-sm"
            >
              {isLoading ? "Getting your recipe…" : "Get recipe"}
            </button>
            <p className="mt-3 text-center text-xs text-[#a89f94]">
              Ctrl+Enter to submit
            </p>
          </section>

          <section className="min-h-[320px]">
            {isLoading ? (
              <div className="rt-panel flex min-h-[320px] items-center justify-center rounded-2xl p-8">
                <Loader label="Composing your recipe" />
              </div>
            ) : recipe ? (
              <div className="space-y-4">
                <RecipeDetail
                  recipe={recipe}
                  statusMessage={saveStatus || undefined}
                  botMessage={botMessage || undefined}
                />
                <div className="flex flex-wrap items-center justify-end gap-3">
                  {!isAuthenticated ? (
                    <Link
                      href="/signin?next=/dashboard"
                      className="text-sm font-semibold text-[#c94c4c] hover:underline"
                    >
                      Sign in to save
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    onClick={handleSaveRecipe}
                    disabled={!isAuthenticated}
                    className="rounded-xl border border-[#e8dfd4] bg-white px-5 py-3 text-sm font-semibold text-[#2d2d2d] transition hover:border-[#c94c4c] hover:text-[#c94c4c] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Save recipe
                  </button>
                </div>
              </div>
            ) : (
              <div className="rt-panel flex min-h-[320px] flex-col items-center justify-center rounded-2xl p-8 text-center">
                <p className="font-brand text-2xl font-semibold text-[#2d2d2d]">Your recipe appears here</p>
                <p className="mt-3 max-w-sm text-sm leading-6 text-[#6b635a]">
                  Add pantry ingredients on the left, choose filters if you like, then hit{" "}
                  <strong className="font-semibold text-[#c94c4c]">Get recipe</strong>.
                </p>
                <div className="mt-8 grid w-full max-w-md gap-3 sm:grid-cols-3">
                  {["One-pot dinners", "Quick & easy", "Cosy comfort"].map((idea) => (
                    <button
                      key={idea}
                      type="button"
                      onClick={() => setPantryInput(idea.toLowerCase())}
                      className="rt-chip rounded-xl px-3 py-3 text-xs font-medium"
                    >
                      {idea}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
