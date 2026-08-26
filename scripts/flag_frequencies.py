"""Per-flag share of assessed hydrological years (Table 4 column).

Aggregates the released per-year evidence file ``camels_ru_year_flags.csv``
(built by ``scripts/create_year_flags.py`` from the released NetCDFs, hard-gated
on full grade parity with ``camels_ru_year_grades.csv``). The census is therefore
an aggregation of the shipped evidence, not an independent recomputation path
that can drift from it.

Writes ``paper/tables/flag_frequencies.csv`` (flag, n_assessed_years, n_years,
share_pct), read by ``scripts/verify_macros.py`` and rendered in
``tables/quality_flags.tex``.

Run: pixi run python scripts/flag_frequencies.py
"""

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
FLAGS = REPO / "release" / "CAMELS_RU_v1.0" / "camels_ru_year_flags.csv"
OUT = REPO / "paper" / "tables" / "flag_frequencies.csv"


def main() -> None:
    """Aggregate the released year-flags file into the per-flag census."""
    yf = pd.read_csv(FLAGS, dtype={"gauge_id": str}).fillna({"flag_codes": ""})
    n_years = len(yf)
    codes = yf["flag_codes"].str.split(",").explode()
    counts = codes[codes != ""].value_counts()
    df = pd.DataFrame(
        {
            "flag": counts.index,
            "n_assessed_years": n_years,
            "n_years": counts.to_numpy(),
            "share_pct": 100.0 * counts.to_numpy() / n_years,
        }
    )
    df.to_csv(OUT, index=False)
    print(f"{yf['gauge_id'].nunique()} gauges, {n_years} assessed years")
    print(df.to_string(index=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
