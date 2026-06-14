import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    results = root / "results" / "hess_quality"
    return csv, results


@app.cell
def _(csv, results):
    def read_rows(name: str) -> list[dict[str, str]]:
        with (results / name).open(newline="") as f:
            return list(csv.DictReader(f))

    length_summary = read_rows("gauge_id_length_summary.csv")
    long_gauge_ids = read_rows("long_gauge_ids.csv")
    return length_summary, long_gauge_ids


@app.cell
def _():
    import marimo as _mo

    _mo.md(
        r"""
# Gauge ID audit

This app checks **only gauge identifiers**: the identifier field detected in each source,
identifier length counts, and which sources contain the long identifiers. The audit treats
`gauge_id`, `Gauge ID`, `GAUGE_ID`, and NetCDF `gauge` as identifier-name variants. It does
not attach HydroATLAS or other attribute columns.
"""
    )
    return


@app.cell
def _(length_summary, long_gauge_ids):
    max_len_gt_7 = max(int(row["len_gt_7"]) for row in length_summary)
    total_long = len(long_gauge_ids)
    id_fields = sorted({row["id_field"] for row in length_summary})
    return id_fields, max_len_gt_7, total_long


@app.cell
def _(id_fields, max_len_gt_7, total_long):
    import marimo as _mo

    _mo.md(
        f"""
## Headline

- Gauge IDs with length **> 7**: **{max_len_gt_7}**
- Gauge IDs with length **>= 7**: **{total_long}**
- Identifier fields detected: `{', '.join(id_fields)}`
"""
    )
    return


@app.cell
def _(length_summary):
    import marimo as _mo

    _mo.md("## Gauge-ID length summary by source")
    _mo.ui.table(length_summary)
    return


@app.cell
def _(long_gauge_ids):
    import marimo as _mo

    _mo.md("## Long gauge IDs by source membership")
    _mo.ui.table(long_gauge_ids)
    return


if __name__ == "__main__":
    app.run()
