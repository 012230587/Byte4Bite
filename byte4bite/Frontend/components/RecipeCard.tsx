interface RecipeCardProps {
  recipe: {
    title: string;
    description: string;
    prep_time?: string;
    difficulty?: string;
    dietary_tags?: string[];
    is_generated?: boolean;
  };
  selected?: boolean;
  onClick?: () => void;
}

const RecipeCard = ({ recipe, selected = false, onClick }: RecipeCardProps) => {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group w-full text-left rounded-3xl border p-5 transition-all ${
        selected ? "border-emerald-400 bg-emerald-50 shadow-lg" : "border-slate-200 bg-white shadow-sm hover:shadow-md"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-900 transition-colors group-hover:text-emerald-600">
            {recipe.title}
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{recipe.description}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-600">
          {recipe.is_generated ? "AI" : "Classic"}
        </span>
      </div>

      <div className="mt-5 flex flex-wrap gap-2 text-xs">
        {recipe.dietary_tags?.map((tag) => (
          <span key={tag} className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-700">
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
        <span>{recipe.prep_time || "30 mins"}</span>
        <span>{recipe.difficulty || "Easy"}</span>
      </div>
    </button>
  );
};

export default RecipeCard;