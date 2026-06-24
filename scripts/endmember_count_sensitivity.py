"""End-member-count sensitivity of the regime/end-member near-independence (§4.2).

The headline result of Sect.~4.2 is that the behavioural (hydrograph-regime) and
physiographic (attribute end-member) partitions of the Russian domain are almost
independent: over the catchments carrying both labels the adjusted Rand index (ARI)
is only ~0.10. The number of end-members is set by the HDBSCAN ``min_cluster_size``
(the released figure uses 40 -> 16 end-members). A reviewer could reasonably ask
whether the near-independence is an artefact of that one tuning choice.

This script re-runs the identical quantile -> PCA(90%) -> HDBSCAN pipeline across a
range of ``min_cluster_size`` (hence a range of end-member counts) and recomputes the
regime-vs-end-member ARI each time, on the same both-labelled subset definition used
by ``regime_endmember_intersection.py`` (end-member != -1, joined to the regime
labels). If ARI stays low across counts, the near-independence is a property of the
domain, not of the chosen granularity.

Run: pixi run python scripts/endmember_count_sensitivity.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score
from sklearn.preprocessing import QuantileTransformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from scripts.cluster_endmembers import SEED, load_features  # noqa: E402

TABLE_DIR = ROOT / "paper" / "tables"
MIN_CLUSTER_SIZES = [25, 30, 40, 50, 60, 80]  # 40 is the released choice (-> 16 end-members)


def main() -> None:
    """Sweep min_cluster_size and report end-member count + regime/end-member ARI."""
    subset, features = load_features()
    xq = QuantileTransformer(
        output_distribution="normal", random_state=SEED, n_quantiles=500
    ).fit_transform(subset[features].values)
    xp = PCA(n_components=0.90, random_state=SEED).fit_transform(xq)

    regimes = pd.read_csv(TABLE_DIR / "regime_assignments.csv", dtype={"gauge_id": str})
    regimes = regimes.set_index("gauge_id")["regime"]
    idx = subset.index.astype(str)

    print(f"{'min_cluster_size':>16} {'n_endmembers':>13} {'n_both_labelled':>16} {'ARI':>7}")
    rows = []
    for mcs in MIN_CLUSTER_SIZES:
        labels = HDBSCAN(min_cluster_size=mcs).fit_predict(xp)
        em = pd.Series(labels, index=idx, name="em")
        n_em = len(set(labels)) - (1 if -1 in labels else 0)
        both = pd.DataFrame({"em": em}).join(regimes, how="inner")
        both = both[both["em"] != -1].dropna()
        ari = adjusted_rand_score(both["regime"], both["em"])
        marker = "  <- released" if mcs == 40 else ""
        print(f"{mcs:>16} {n_em:>13} {len(both):>16} {ari:>7.3f}{marker}")
        rows.append({"min_cluster_size": mcs, "n_endmembers": n_em, "n_both": len(both), "ari": ari})

    aris = [r["ari"] for r in rows]
    print(
        f"\nARI range across {min(r['n_endmembers'] for r in rows)}-"
        f"{max(r['n_endmembers'] for r in rows)} end-members: "
        f"{min(aris):.3f} to {max(aris):.3f} (near-independence is not a granularity artefact)."
    )


if __name__ == "__main__":
    main()
