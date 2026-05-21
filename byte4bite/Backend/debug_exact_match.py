from services.recipe_service import _load_all_recipes

recipes = _load_all_recipes()
term = 'dal makhani'
matches = [r for r in recipes if r['title'].strip().lower() == term]
print(f'Exact title matches for {term}: {len(matches)}')
for i, r in enumerate(matches[:5], 1):
    print(f'--- Match {i} ---')
    print('Title:', r['title'])
    print('Description:', r['description'])
    print('Ingredients:', r['ingredients'][:10])
    print('Instructions:', r['instructions'][:5])
    print()