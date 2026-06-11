-- =============================================================================
-- Byte4Bite — Clear ALL recipe memory (bookmarks + user-saved copies)
-- Run in MySQL Workbench. Also clears memory_store.json via:
--   python -m rag.ingest --clear-memory
-- =============================================================================

USE byte4bite;

SELECT COUNT(*) AS saved_recipes_before FROM saved_recipes;
SELECT COUNT(*) AS user_saved_before
FROM asian_recipes WHERE source_file = 'user_saved';

DELETE FROM saved_recipes WHERE saved_id > 0;

DELETE FROM asian_recipes
WHERE source_file = 'user_saved' AND recipe_id > 0;

SELECT COUNT(*) AS saved_recipes_after FROM saved_recipes;
SELECT COUNT(*) AS user_saved_after
FROM asian_recipes WHERE source_file = 'user_saved';

-- Dataset corpus (Excel/CSV ingested recipes) is NOT deleted here.
-- To wipe the full search corpus too, run clean_recipe_corpus.sql instead.
