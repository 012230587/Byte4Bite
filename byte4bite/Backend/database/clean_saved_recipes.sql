-- =============================================================================
-- Byte4Bite — Clean saved recipes (user bookmarks only)
-- Run in MySQL Workbench against your byte4bite database.
--
-- This removes:
--   1. saved_recipes     — user bookmark links
--   2. asian_recipes rows where source_file = 'user_saved'
--      (generated/saved copies that still appear in ingredient SEARCH otherwise)
--
-- It does NOT delete dataset recipes (CSV source_file values) or user accounts.
-- =============================================================================

USE byte4bite;

-- Preview counts before deleting
SELECT COUNT(*) AS saved_recipes_before_delete
FROM saved_recipes;

SELECT COUNT(*) AS user_saved_corpus_before_delete
FROM asian_recipes
WHERE source_file = 'user_saved';

-- Optional: inspect what will be removed
-- SELECT s.saved_id, s.user_id, u.email, r.title, s.saved_at
-- FROM saved_recipes s
-- JOIN users u ON u.user_id = s.user_id
-- JOIN asian_recipes r ON r.recipe_id = s.recipe_id
-- ORDER BY s.saved_at DESC;

-- ---------------------------------------------------------------------------
-- Option A (default): delete ALL saved recipes for every user
-- Uses saved_id (PRIMARY KEY) so MySQL Workbench safe-update mode allows it.
-- ---------------------------------------------------------------------------
DELETE FROM saved_recipes WHERE saved_id > 0;

-- Step 2: remove user-saved copies from the search corpus (safe-update compatible)
DELETE FROM asian_recipes
WHERE source_file = 'user_saved' AND recipe_id > 0;

-- ---------------------------------------------------------------------------
-- Option B: delete saved recipes for ONE user only (comment Option A first)
-- Replace 1 with the target user_id from: SELECT user_id, email FROM users;
-- ---------------------------------------------------------------------------
-- DELETE FROM saved_recipes WHERE user_id = 1;

-- ---------------------------------------------------------------------------
-- Option C: delete saved recipes for ONE user by email (comment Option A first)
-- ---------------------------------------------------------------------------
-- DELETE sr
-- FROM saved_recipes sr
-- JOIN users u ON u.user_id = sr.user_id
-- WHERE u.email = 'user@example.com';

-- Confirm cleanup
SELECT COUNT(*) AS saved_recipes_after_delete
FROM saved_recipes;

SELECT COUNT(*) AS user_saved_corpus_after_delete
FROM asian_recipes
WHERE source_file = 'user_saved';
