-- =============================================================================
-- Phase A: Semantic search embeddings (Byte4Bite)
-- =============================================================================
-- MySQL 8.0: NO column type change required.
--   embedding VARBINARY(3072) already stores 768 x float32 (see schema.sql).
--
-- Application changes (not SQL):
--   EMBEDDING_MODEL=gemini-embedding-001  (text-embedding-004 is deprecated/404)
--   output_dimensionality=768 via Google GenAI SDK
--   EMBED_ON_INGEST=true
--
-- After deploy, backfill existing zero vectors:
--   cd Backend && python -m rag.backfill_embeddings
--
-- Verify retrieval:
--   cd Backend && python scripts/verify_semantic_search.py
-- =============================================================================

USE byte4bite;

-- Optional: index to speed corpus scans during backfill (safe on MySQL 8.0)
-- Skip if idx_asian_recipes_source already exists from a prior run.
SET @idx_exists := (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'asian_recipes'
      AND index_name = 'idx_asian_recipes_source_file'
);

SET @sql := IF(
    @idx_exists = 0,
    'CREATE INDEX idx_asian_recipes_source_file ON asian_recipes (source_file)',
    'SELECT ''idx_asian_recipes_source_file already exists'' AS note'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Corpus health check (zero blobs = needs backfill)
SELECT
    COUNT(*) AS total_corpus,
    SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) AS null_embeddings,
    SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS has_blob
FROM asian_recipes
WHERE source_file IS NULL OR source_file <> 'user_saved';
