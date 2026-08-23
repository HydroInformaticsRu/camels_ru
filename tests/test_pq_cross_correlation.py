"""P-Q cross-correlation: calendar-day lags, evaluated on incomplete years too."""

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from quality.meteo_response import calculate_pq_cross_correlation  # noqa: E402

rng = np.random.default_rng(0)
idx = pd.date_range("2010-01-01", "2010-12-31", freq="D")
p = pd.Series(rng.gamma(0.5, 4.0, len(idx)), index=idx)
q = p.shift(3).fillna(0.0) + rng.normal(0, 0.1, len(idx))  # Q responds 3 days after P

full = calculate_pq_cross_correlation(p, q)
assert full["optimal_lag_days"] == 3, full

# Positional lagging after dropna would mis-lag across this gap; calendar lagging must not.
q_gappy = q.copy()
q_gappy.loc["2010-04-10":"2010-05-20"] = np.nan
gappy = calculate_pq_cross_correlation(p, q_gappy)
assert gappy["optimal_lag_days"] == 3, gappy
assert abs(gappy["max_cross_correlation"] - full["max_cross_correlation"]) < 0.05

# Too few pairs -> NaN, not an exception
sparse = calculate_pq_cross_correlation(p.iloc[:20], q.iloc[:20])
assert np.isnan(sparse["max_cross_correlation"])
print("ok")
