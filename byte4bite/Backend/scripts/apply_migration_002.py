"""Apply Phase E search_history.search_mode column if missing."""
from database.connection import get_connection


def main() -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'search_history'
              AND column_name = 'search_mode'
            """
        )
        exists = int(cur.fetchone()[0])
        if exists:
            print("search_mode column already exists")
        else:
            cur.execute(
                """
                ALTER TABLE search_history
                ADD COLUMN search_mode VARCHAR(32) NULL DEFAULT 'browse' AFTER query_text
                """
            )
            print("Added search_mode column")
        cur.close()


if __name__ == "__main__":
    main()
