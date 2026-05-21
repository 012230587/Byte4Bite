from services.recipe_service import _load_all_recipes, _validate_recipe_integrity

recipes = _load_all_recipes()
validated = [r for r in recipes if _validate_recipe_integrity(r)]

print(f'Total recipes: {len(recipes)}')
print(f'Validated recipes: {len(validated)}')
print(f'Filtered out: {len(recipes) - len(validated)} corrupted recipes')

print('\nValidated recipes:')
for i, recipe in enumerate(validated[:10]):
    print(f'{i+1}. {recipe["title"]}')

print('\nSample validated recipe details:')
if validated:
    recipe = validated[0]
    print(f'Title: {recipe["title"]}')
    print(f'Description: {recipe["description"]}')
    print(f'Ingredients: {recipe["ingredients"][:3]}')  # First 3 ingredients
    print(f'Instructions: {len(recipe["instructions"])} steps')