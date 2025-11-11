import os
import glob
import pandas as pd

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../..")) 
DATA_DIR = os.path.join(ROOT_DIR, "data", "csv")
PATTERN = os.path.join(DATA_DIR, "pr_labels_year-long-project-team-*.csv")
SAVE_FORMAT = "%Y-%m-%d %H:%M:%S%z"  # e.g., 2023-10-01 12:49:05+00:00


def standardize_timestamp_column(df: pd.DataFrame, col_name: str) -> pd.Series:
    """
    Convert timestamp column to UTC with consistent format.
    Handles UTC (Z) and PDT/PST (-07:00/-08:00) formats.
    """
    if col_name not in df.columns:
        print(f"[WARN] Column '{col_name}' missing — skipping.")
        return pd.Series([pd.NaT] * len(df))

    s = df[col_name].astype(str).str.strip()

    # fix space vs T separator before timezone offsets (pandas needs ISO 8601)
    s = s.str.replace(
        r"(?<=\d{2}) (?=\d{2}:\d{2}:\d{2}[-+]\d{2}:\d{2})", "T", regex=True
    )

    # parse to datetime
    ts = pd.to_datetime(s, utc=True, errors="coerce")

    # format output as desired
    return ts.dt.strftime("%Y-%m-%d %H:%M:%S%z")


def main():
    files = glob.glob(PATTERN)
    if not files:
        print(f"[INFO] No matching files found in {DATA_DIR}")
        return

    print(f"[INFO] Found {len(files)} PR label files to process.\n")

    for fp in files:
        try:
            df = pd.read_csv(fp)
            print(f"[PROCESSING] {os.path.basename(fp)}")

            # Only convert merged_at and updated_at
            for col in ["merged_at", "updated_at"]:
                if col in df.columns:
                    df[col] = standardize_timestamp_column(df, col)

            # Overwrite the same file
            df.to_csv(fp, index=False)
            print(f"  → Updated {os.path.basename(fp)} successfully.\n")

        except Exception as e:
            print(f"[ERROR] Failed to process {fp}: {e}\n")

    print("[DONE] All timestamp conversions complete.")

if __name__ == "__main__":
    main()
