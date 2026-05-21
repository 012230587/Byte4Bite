import os
import pandas as pd

DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")
COMMON_COLUMNS = ["instructions", "description", "ingredients", "recipe_instructions", "recipe_ingredients"]


def clean_text(value):
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    return text


def sanitize_csv(file_path: str):
    print(f"Sanitizing: {file_path}")
    df = pd.read_csv(file_path, dtype=str, engine='python')
    sanitized = False

    for column in df.columns:
        if column.strip().lower() in COMMON_COLUMNS or any(key in column.strip().lower() for key in COMMON_COLUMNS):
            df[column] = df[column].apply(clean_text)
            sanitized = True

    if sanitized:
        df.to_csv(file_path, index=False)
        print(f"  Updated file: {file_path}")
    else:
        print(f"  No matching text columns found in {file_path}")


if __name__ == "__main__":
    for filename in os.listdir(DATASETS_DIR):
        if filename.lower().endswith('.csv'):
            sanitize_csv(os.path.join(DATASETS_DIR, filename))
    print("Dataset sanitization complete.")
