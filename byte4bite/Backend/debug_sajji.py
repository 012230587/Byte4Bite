from services.recipe_service import _load_all_recipes, _validate_recipe_integrity

recipes = _load_all_recipes()
sajji_recipes = [r for r in recipes if 'sajji' in r['title'].lower()]

print(f'Found {len(sajji_recipes)} Sajji recipes')

for i, recipe in enumerate(sajji_recipes[:2]):  # Check first 2 Sajji recipes
    print(f'=== Sajji Recipe {i+1} ===')
    print(f'Title: {recipe["title"]}')
    print(f'Ingredients: {recipe["ingredients"][:5]}')  # First 5 ingredients
    ingredients_text = ' '.join(recipe.get('ingredients', [])).lower()
    print(f'Ingredients text: {ingredients_text[:100]}...')

    # Check validation rules
    title = recipe.get('title', '').lower()
    expected_ingredients = ['meat', 'spices', 'yogurt', 'onion']
    has_expected = any(expected in ingredients_text for expected in expected_ingredients)
    print(f'Has expected ingredients (meat/spices/yogurt/onion): {has_expected}')

    print(f'Valid: {_validate_recipe_integrity(recipe)}')
    print()