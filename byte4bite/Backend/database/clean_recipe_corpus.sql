-- =============================================================================
-- Byte4Bite — Delete ALL ingested recipes from MySQL
-- Run in MySQL Workbench against your byte4bite database.
--
-- Removes the entire recipe knowledge base (asian_recipes) from earlier ingests.
-- saved_recipes bookmarks are removed first (FK-safe); user accounts are kept.
--
-- After this, reload from CSV:
--   cd Backend
--   python -m rag.ingest --refresh --no-embed
-- =============================================================================

USE byte4bite;

SELECT COUNT(*) AS corpus_before_delete
FROM asian_recipes;

SELECT COUNT(*) AS saved_bookmarks_before_delete
FROM saved_recipes;

-- Step 1: clear bookmarks (safe-update compatible)
DELETE FROM saved_recipes WHERE saved_id > 0;

-- Step 2: delete entire ingested corpus (safe-update compatible)
DELETE FROM asian_recipes WHERE recipe_id > 0;

-- Confirm empty corpus
SELECT COUNT(*) AS corpus_after_delete
FROM asian_recipes;

SELECT COUNT(*) AS saved_bookmarks_after_delete
FROM saved_recipes;
