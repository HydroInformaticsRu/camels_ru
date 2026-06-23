"""Regression test: GLEAM4 PET must not be scaled by 1000 on aggregation.

GLEAM4 potential evaporation is already in mm/day in the parsed per-gauge
CSVs, so its unit-conversion factor must be 1.0. The released forcing was
correct only because ``potential_evaporation`` happened to be absent from the
aggregation's ``conversion_vars`` set, so the (wrong) factor of 1000 was never
applied -- a two-errors-cancel latent trap (2026-06 science-review, Domain
Expert finding): adding ``potential_evaporation`` to ``conversion_vars`` would
have inflated PET by 1000x. Make the factor correct so the trap cannot fire.

Run: ``pixi run python tests/test_gleam_pet_units.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from src.meteo.aggregation import get_unit_conversion  # noqa: E402


def test_gleam_pet_is_native_mm_per_day() -> None:
    """GLEAM4 PET is native mm/day; its conversion factor must be 1.0."""
    assert get_unit_conversion("gleam") == 1.0, (
        "GLEAM4 PET is already mm/day in the parsed CSVs; a factor != 1.0 would "
        "inflate PET if potential_evaporation were added to conversion_vars"
    )


if __name__ == "__main__":
    test_gleam_pet_is_native_mm_per_day()
    print("PASS: test_gleam_pet_units")
