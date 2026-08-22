"""Köppen-Geiger climate classification from monthly climatologies.

Implements the criteria of Peel et al. (2007, Table 1) for a single location
given 12 monthly mean air temperatures (°C) and 12 monthly precipitation totals
(mm), January to December. The arid (B) criterion is evaluated first, as in the
reference implementation. Summer is the warmer of the two half-years
(April-September or October-March), which makes the function hemisphere-agnostic.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

_SUMMER_N = np.array([3, 4, 5, 6, 7, 8])  # April-September (0-based month index)
_WINTER_N = np.array([9, 10, 11, 0, 1, 2])


def _halves(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (summer, winter) month indices, summer being the warmer half-year."""
    if t[_SUMMER_N].mean() >= t[_WINTER_N].mean():
        return _SUMMER_N, _WINTER_N
    return _WINTER_N, _SUMMER_N


def _precip_threshold(mat: float, map_: float, p_summer: float, p_winter: float) -> float:
    """Precipitation threshold separating arid (B) climates, after Peel et al. (2007)."""
    if p_winter >= 0.7 * map_:
        return 2.0 * mat
    if p_summer >= 0.7 * map_:
        return 2.0 * mat + 28.0
    return 2.0 * mat + 14.0


def _seasonality(p: np.ndarray, summer: np.ndarray, winter: np.ndarray) -> str:
    """Second letter for C and D climates: s (dry summer), w (dry winter), or f."""
    psdry, pswet = p[summer].min(), p[summer].max()
    pwdry, pwwet = p[winter].min(), p[winter].max()
    dry_summer = psdry < 40.0 and psdry < pwwet / 3.0
    dry_winter = pwdry < pswet / 10.0
    if dry_summer and dry_winter:
        return "s" if p[winter].sum() > p[summer].sum() else "w"
    if dry_summer:
        return "s"
    if dry_winter:
        return "w"
    return "f"


def _warmth(t: np.ndarray, cold_allowed: bool) -> str:
    """Third letter for C and D climates (a, b, c, or d for D only)."""
    thot, tcold = t.max(), t.min()
    tmon10 = int((t > 10.0).sum())
    if thot >= 22.0:
        return "a"
    if tmon10 >= 4:
        return "b"
    if cold_allowed and tcold < -38.0:
        return "d"
    return "c"


def classify_koppen(t_monthly: Iterable[float], p_monthly: Iterable[float]) -> str:
    """Return the Köppen-Geiger class for one location.

    Args:
        t_monthly: Twelve monthly mean air temperatures (°C), January to December.
        p_monthly: Twelve monthly precipitation totals (mm), January to December.

    Returns:
        The two- or three-letter class, e.g. ``"Dfb"``, ``"BSk"``, ``"ET"``.
        Returns ``""`` when any input is not finite.
    """
    t = np.asarray(list(t_monthly), dtype=float)
    p = np.asarray(list(p_monthly), dtype=float)
    if t.shape != (12,) or p.shape != (12,) or not (np.isfinite(t).all() and np.isfinite(p).all()):
        return ""
    summer, winter = _halves(t)
    mat, map_ = float(t.mean()), float(p.sum())
    thot, tcold, pdry = float(t.max()), float(t.min()), float(p.min())
    threshold = _precip_threshold(mat, map_, float(p[summer].sum()), float(p[winter].sum()))

    if map_ < 10.0 * threshold:
        return ("BW" if map_ < 5.0 * threshold else "BS") + ("h" if mat >= 18.0 else "k")
    if tcold >= 18.0:
        if pdry >= 60.0:
            return "Af"
        return "Am" if pdry >= 100.0 - map_ / 25.0 else "Aw"
    if thot <= 10.0:
        return "ET" if thot > 0.0 else "EF"
    if tcold > 0.0:
        return "C" + _seasonality(p, summer, winter) + _warmth(t, cold_allowed=False)
    return "D" + _seasonality(p, summer, winter) + _warmth(t, cold_allowed=True)
