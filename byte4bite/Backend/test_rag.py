from rag.retriever import find_best_recipes

results = find_best_recipes('sajji', top_k=3)
print(f'Found {len(results)} recipes for "sajji":')
for i, recipe in enumerate(results):
    print(f'{i+1}. {recipe["title"]}')
    ingredients = recipe.get('ingredients', [])[:3]
    print(f'   Ingredients: {ingredients}')
    print()