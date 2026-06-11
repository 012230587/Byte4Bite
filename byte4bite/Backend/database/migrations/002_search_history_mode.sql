-- Phase E: log browse vs compose searches in search_history
USE byte4bite;

SET @col_exists := (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'search_history'
      AND column_name = 'search_mode'
);

SET @sql := IF(
    @col_exists = 0,
    "ALTER TABLE search_history ADD COLUMN search_mode VARCHAR(32) NULL DEFAULT 'browse' AFTER query_text",
    "SELECT 'search_mode column already exists' AS note"
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
