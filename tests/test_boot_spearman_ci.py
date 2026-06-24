"""Regression test: bootstrap CI on the cold-arm Spearman rho (n=126).

The §4 permafrost-BFI sign reversal reports warm/cold Spearman rho with p-values
only; the Domain Expert (2026-06 science review) asked for a bootstrap CI on the
small cold arm (n=126). ``boot_spearman_ci`` must be reproducible independent of
call order (a local seeded RNG, not the module global) so verify_macros can lock
the reported interval.

Run: ``pixi run python tests/test_boot_spearman_ci.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys

import numpy as np
from scipy.stats import spearmanr

sys.path.append(str(Path(__file__).parent.parent))
from scripts.coldregion_robustness import boot_spearman_ci  # noqa: E402


def test_point_matches_spearman() -> None:
    """The point estimate equals scipy's Spearman rho on the observed pairs."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    y = 0.5 * x + rng.normal(size=200)
    rho, lo, hi = boot_spearman_ci(x, y, seed=1996)
    assert abs(rho - spearmanr(x, y)[0]) < 1e-9, rho
    assert lo < rho < hi, (lo, rho, hi)


def test_reproducible_for_fixed_seed() -> None:
    """Same seed + same data -> identical interval (order-independent RNG)."""
    x = np.arange(50.0)
    y = np.arange(50.0) ** 1.3
    assert boot_spearman_ci(x, y, seed=1996) == boot_spearman_ci(x, y, seed=1996)


def test_perfect_monotonic_gives_unit_interval() -> None:
    """A perfectly monotonic relation -> rho ~1.0 and a degenerate [1, 1] CI.

    (Spearman of ranks returns 0.999...9, not bit-exact 1.0, so allow tolerance.)
    """
    x = np.arange(100.0)
    y = 2.0 * x + 1.0
    rho, lo, hi = boot_spearman_ci(x, y, seed=1996)
    assert abs(rho - 1.0) < 1e-9, rho
    assert abs(lo - 1.0) < 1e-9 and abs(hi - 1.0) < 1e-9, (lo, hi)


def test_drops_nan_pairs() -> None:
    """Pairs with a NaN in either coordinate are excluded before correlating."""
    x = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    y = np.array([1.0, 2.0, 3.0, np.nan, 5.0])
    rho, lo, hi = boot_spearman_ci(x, y, seed=1996)  # only (1,1),(2,2),(3,3) complete
    assert abs(rho - 1.0) < 1e-9, rho
    assert lo <= rho <= hi, (lo, rho, hi)


if __name__ == "__main__":
    test_point_matches_spearman()
    test_reproducible_for_fixed_seed()
    test_perfect_monotonic_gives_unit_interval()
    test_drops_nan_pairs()
    print("PASS: test_boot_spearman_ci")
