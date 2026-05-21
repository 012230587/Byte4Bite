from services.recipe_service import _load_all_recipes

recipes = _load_all_recipes()
from collections import defaultdict

by_title = defaultdict(list)
for r in recipes:
    by_title[r['title'].strip().lower()].append(r)

print('Duplicate title counts:')
for title, items in sorted(by_title.items(), key=lambda x: -len(x[1]))[:20]:
    if len(items) > 1:
        print(f'{title!r}: {len(items)}')

# Show sample duplicates
for title, items in by_title.items():
    if title in {'sajji', 'dal makhani', 'biryani', 'thailand green curry', 'thai green curry', 'japanese ramen'}:
        print('\n===', title, '===> count', len(items))
        for i, r in enumerate(items[:3]):
            print(i+1, r['title'], r['ingredients'][:5])
