interface RecipeDetailProps {
  recipe: {
    title: string;
    description?: string;
    ingredients: string[] | string;
    instructions: string[] | string;
    prep_time?: string;
    difficulty?: string;
    dietary_tags?: string[];
    is_generated?: boolean;
  } | null;
  statusMessage?: string;
}

export default function RecipeDetail({ recipe, statusMessage }: RecipeDetailProps) {
  if (!recipe) {
    return (
      <div className="rounded-[2rem] border border-slate-200 bg-white/90 p-6 shadow-sm shadow-slate-200">
        <div className="text-slate-900 text-lg font-semibold mb-3">Recipe Preview</div>
        <p className="text-slate-600 leading-relaxed">
          Select a recipe from the list or generate a custom dish from your ingredients to see step-by-step culinary directions here.
        </p>
        {statusMessage ? <p className="mt-4 text-sm text-emerald-700">{statusMessage}</p> : null}
      </div>
    );
  }

  const ingredients = Array.isArray(recipe.ingredients)
    ? recipe.ingredients
    : typeof recipe.ingredients === "string"
    ? recipe.ingredients.split(/,\s*/).filter(Boolean)
    : [];

  const instructions = Array.isArray(recipe.instructions)
    ? recipe.instructions.filter(Boolean)
    : typeof recipe.instructions === "string"
    ? [recipe.instructions.trim()]
    : [];

  const instructionsText = instructions
    .map((step, index) => `${index + 1}. ${step}`)
    .join("\n\n");

  return (
    <div className="rounded-[2rem] border border-slate-200 bg-white/95 p-6 shadow-sm shadow-slate-200">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">{recipe.title}</h2>
          <p className="mt-2 text-slate-600">{recipe.description || "A chef-crafted recipe ready for your kitchen."}</p>
        </div>
        <div className="rounded-3xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm">
          {recipe.is_generated ? "AI-Generated" : "Recipe"}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 mb-6">
        <div className="rounded-3xl bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Prep & difficulty</p>
          <div className="text-slate-900 font-semibold">{recipe.prep_time || "30 mins"}</div>
          <div className="mt-1 text-slate-600">{recipe.difficulty || "Easy"}</div>
        </div>
        <div className="rounded-3xl bg-slate-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-2">Tags</p>
          <div className="flex flex-wrap gap-2">
            {(recipe.dietary_tags || []).map((tag) => (
              <span key={tag} className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                {tag}
              </span>
            ))}
            {!recipe.dietary_tags?.length ? (
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">No tags</span>
            ) : null}
          </div>
        </div>
      </div>

      <section className="mb-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-3">Ingredients</h3>
        <div className="grid gap-2 sm:grid-cols-2">
          {ingredients.map((ingredient, index) => (
            <div key={`${ingredient}-${index}`} className="rounded-3xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
              {ingredient}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-lg font-semibold text-slate-900 mb-3">Cooking Steps</h3>
        <div className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
          <p className="whitespace-pre-wrap text-slate-700 leading-relaxed">{instructionsText}</p>
        </div>
      </section>

      {statusMessage ? (
        <div className="mt-6 rounded-3xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {statusMessage}
        </div>
      ) : null}
    </div>
  );
}
