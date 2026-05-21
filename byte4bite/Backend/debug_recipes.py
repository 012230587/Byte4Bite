from services.recipe_service import _load_all_recipes

recipes = _load_all_recipes()
print(f'Total recipes loaded: {len(recipes)}')

print('\nFirst 5 recipes:')
for i, recipe in enumerate(recipes[:5]):
    print(f'{i+1}. {recipe["title"]}')
    ingredients = recipe.get('ingredients', [])
    print(f'   Ingredients: {ingredients[:2] if ingredients else "None"}...')
    print()

print('\nLast 5 recipes:')
for i, recipe in enumerate(recipes[-5:]):
    print(f'{len(recipes)-4+i}. {recipe["title"]}')
    ingredients = recipe.get('ingredients', [])
    print(f'   Ingredients: {ingredients[:2] if ingredients else "None"}...')
    print()