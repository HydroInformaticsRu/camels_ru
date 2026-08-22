"""Köppen-Geiger classifier self-check on approximate station normals."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.meteo.koppen import classify_koppen

CASES = {
    # Moscow: humid continental, warm summer
    "Dfb": (
        [-6.5, -6.7, -1.0, 6.7, 13.2, 17.0, 19.2, 17.0, 11.3, 5.6, -1.2, -5.2],
        [52, 41, 35, 37, 49, 80, 85, 82, 68, 71, 55, 52],
    ),
    # Yakutsk: extremely cold winter (Tcold < -38), three months above 10 °C
    "Dfd": (
        [-38.6, -33.8, -20.1, -4.8, 7.5, 16.4, 19.5, 15.2, 6.1, -7.8, -27.0, -37.0],
        [9, 6, 5, 7, 17, 37, 39, 37, 30, 18, 16, 12],
    ),
    # Astrakhan: cold semi-arid steppe
    "BSk": (
        [-3.5, -2.7, 3.5, 11.5, 18.5, 23.5, 26.0, 24.5, 18.0, 10.0, 3.0, -1.5],
        [15, 12, 15, 18, 25, 25, 20, 20, 20, 18, 20, 20],
    ),
    # Chita: dry-winter subarctic
    "Dwc": (
        [-25.0, -20.0, -10.0, 1.0, 9.5, 16.0, 18.8, 16.0, 8.5, -1.0, -14.0, -23.0],
        [3, 2, 3, 10, 25, 60, 95, 85, 35, 10, 6, 4],
    ),
    # Dikson: Arctic tundra
    "ET": (
        [-26.0, -26.0, -24.0, -17.0, -8.0, 0.5, 5.0, 5.5, 1.5, -8.0, -18.0, -23.0],
        [20] * 12,
    ),
    # Sochi: humid subtropical
    "Cfa": (
        [6.0, 6.5, 8.5, 12.0, 16.5, 21.0, 23.5, 24.0, 20.5, 16.0, 11.5, 8.0],
        [180, 130, 120, 110, 90, 100, 100, 120, 130, 150, 200, 190],
    ),
}


def test_known_stations() -> None:
    for expected, (t, p) in CASES.items():
        assert classify_koppen(t, p) == expected, (expected, classify_koppen(t, p))


def test_nan_input_returns_empty() -> None:
    assert classify_koppen([float("nan")] * 12, [10] * 12) == ""


if __name__ == "__main__":
    test_known_stations()
    test_nan_input_returns_empty()
    print("ok")
