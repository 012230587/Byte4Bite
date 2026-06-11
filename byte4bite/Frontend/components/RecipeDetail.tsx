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
    cuisine?: string;
    inspired_by?: string[];
    retrieval_note?: string;
  } | null;
  statusMessage?: string;
  botMessage?: string;
}

export default function RecipeDetail({ recipe, statusMessage, botMessage }: RecipeDetailProps) {
  if (!recipe) {
    return null;
  }

  const ingredients = Array.isArray(recipe.ingredients)
    ? recipe.ingredients
    : typeof recipe.ingredients === "string"
    ? recipe.ingredients.split(/,\s*/).filter(Boolean)
    : [];

  const instructions = Array.isArray(recipe.instructions)
    ? recipe.instructions.filter(Boolean)
    : typeof recipe.instructions === "string"
    ? recipe.instructions
        .split(/\n+|(?<=\.)\s+(?=\d+[\).]\s+)/)
        .map((s) => s.trim())
        .filter(Boolean)
    : [];

  return (
    <article className="rt-panel overflow-hidden rounded-2xl">
      <div className="border-b border-[#e8dfd4] bg-[#f3ebe0] px-6 py-5 sm:px-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[#c94c4c]">
              {recipe.cuisine ? `${recipe.cuisine} · ` : ""}
              {recipe.prep_time || "30 mins"} · {recipe.difficulty || "Easy"}
            </p>
            <h2 className="font-brand mt-2 text-3xl font-bold leading-tight text-[#2d2d2d]">
              {recipe.title}
            </h2>
            <p className="mt-3 text-[#6b635a] leading-relaxed">
              {recipe.description || "A complete home-cooked dish built from your pantry."}
            </p>
          </div>
          <span className="rounded-full bg-[#c94c4c] px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white">
            Tailored
          </span>
        </div>
      </div>

      <div className="space-y-6 px-6 py-6 sm:px-8">
        {botMessage ? (
          <div className="rounded-xl border border-[#e8dfd4] bg-[#faf7f2] px-4 py-3 text-sm text-[#2d2d2d]">
            <p className="font-semibold text-[#c94c4c]">Byte4Bite</p>
            <p className="mt-1 leading-relaxed">{botMessage}</p>
          </div>
        ) : null}

        {recipe.inspired_by && recipe.inspired_by.length > 0 ? (
          <div className="rounded-xl border border-[#e8dfd4] bg-white px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#a89f94]">
              Inspired by corpus matches
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {recipe.inspired_by.map((title) => (
                <li
                  key={title}
                  className="rounded-full bg-[#f3ebe0] px-3 py-1 text-xs font-medium text-[#6b635a]"
                >
                  {title}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {(recipe.dietary_tags || []).length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {recipe.dietary_tags!.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[#e8dfd4] bg-[#faf7f2] px-3 py-1 text-xs font-semibold text-[#6b635a]"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}

        <section>
          <h3 className="font-brand text-xl font-semibold text-[#2d2d2d]">Ingredients</h3>
          <ul className="mt-4 space-y-2">
            {ingredients.map((ingredient, index) => (
              <li
                key={`${ingredient}-${index}`}
                className="flex gap-3 rounded-lg border border-[#f3ebe0] bg-[#faf7f2] px-4 py-2.5 text-sm text-[#2d2d2d]"
              >
                <span className="text-[#c94c4c]">•</span>
                <span>{ingredient}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="font-brand text-xl font-semibold text-[#2d2d2d]">Method</h3>
          <ol className="mt-4 list-decimal space-y-4 ps-5 text-[#2d2d2d] leading-relaxed">
            {instructions.map((step, index) => (
              <li key={`step-${index}`} className="ps-1">
                {step.replace(/^\s*\d+[\).]\s*/, "")}
              </li>
            ))}
          </ol>
        </section>

        {statusMessage ? (
          <p className="rounded-xl bg-[#f3ebe0] px-4 py-3 text-sm text-[#6b635a]">{statusMessage}</p>
        ) : null}
      </div>
    </article>
  );
}
