-- =============================================================================
-- Byte4Bite MySQL Schema (MySQL 8.0+)
-- Execute this script in MySQL Workbench against your target database.
--
-- Embeddings are stored as VARBINARY(3072) = 768 float32 values packed via
-- numpy.tobytes(). This works on MySQL 8.0. MySQL 9.0+ users may optionally
-- migrate the column to VECTOR(768) for native DISTANCE() indexing.
--
-- Data flow:
--   users ──< user_profiles
--   users ──< search_history
--   users ──< saved_recipes >── asian_recipes (knowledge base + binary embeddings)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS byte4bite
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE byte4bite;

-- -----------------------------------------------------------------------------
-- 1. Core accounts
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email         VARCHAR(255)    NOT NULL,
    password_hash VARCHAR(255)    NOT NULL COMMENT 'bcrypt or argon2 hash — never store plaintext',
    created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 2. Personalized health / dietary profile (1:1 with users)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id              BIGINT UNSIGNED NOT NULL,
    dietary_restriction  VARCHAR(100)    NULL COMMENT 'e.g. vegetarian, vegan, halal, gluten-free',
    allergies            JSON            NULL COMMENT '["peanuts","shellfish"]',
    health_goals         JSON            NULL COMMENT '["weight_loss","high_protein"]',
    updated_at           TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (profile_id),
    UNIQUE KEY uq_user_profiles_user (user_id),
    CONSTRAINT fk_user_profiles_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3. Search audit trail
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_history (
    history_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id      BIGINT UNSIGNED NULL COMMENT 'NULL for anonymous searches',
    query_text   VARCHAR(500)    NOT NULL,
    search_mode  VARCHAR(32)     NULL DEFAULT 'browse' COMMENT 'browse | compose',
    searched_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (history_id),
    KEY idx_search_history_user_time (user_id, searched_at DESC),
    CONSTRAINT fk_search_history_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 4. Local Asian recipe knowledge base (RAG corpus)
--    UNIQUE title prevents duplicate ingestion at the DB layer.
--    embedding: VARBINARY(3072) = 768 dimensions × 4 bytes (gemini-embedding-001)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asian_recipes (
    recipe_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title         VARCHAR(512)    NOT NULL,
    description   TEXT            NULL,
    ingredients   JSON            NOT NULL COMMENT '["250g chicken","2 tbsp soy sauce"]',
    instructions  JSON            NOT NULL COMMENT '["Step 1...","Step 2..."]',
    prep_time     VARCHAR(64)     NULL DEFAULT '30 mins',
    difficulty    ENUM('Easy','Medium','Hard') NOT NULL DEFAULT 'Medium',
    cuisine       VARCHAR(100)    NULL,
    dietary_tags  JSON            NULL COMMENT '["vegetarian","halal"]',
    source_file   VARCHAR(255)    NULL COMMENT 'Originating CSV filename',
    embedding     VARBINARY(3072) NULL COMMENT 'gemini-embedding-001: np.float32[768].tobytes()',
    created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (recipe_id),
    UNIQUE KEY uq_asian_recipes_title (title),
    KEY idx_asian_recipes_cuisine (cuisine),
    KEY idx_asian_recipes_difficulty (difficulty)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 5. User bookmarks
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_recipes (
    saved_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED NOT NULL,
    recipe_id   BIGINT UNSIGNED NOT NULL,
    notes       VARCHAR(500)    NULL,
    saved_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (saved_id),
    UNIQUE KEY uq_saved_recipes_user_recipe (user_id, recipe_id),
    KEY idx_saved_recipes_user (user_id, saved_at DESC),
    CONSTRAINT fk_saved_recipes_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_saved_recipes_recipe
        FOREIGN KEY (recipe_id) REFERENCES asian_recipes (recipe_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
