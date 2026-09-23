from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
import numpy as np
import pandas as pd
import xarray as xr
from src.hydro.flow_extremes import FlowExtremes
from src.hydro.flow_variability import FlowVariability
root = Path('release/CAMELS_RU_v1.0')
sig = pd.read_csv(root / 'camels_ru_signatures.csv', dtype={'gauge_id':str}).set_index('gauge_id')
with xr.open_dataset(root / 'camels_ru_discharge.nc') as ds:
    q = ds.discharge_mm.sel(gauge_id=sig.index.tolist(),time=slice('2008-10-01','2023-09-30')).load()
dates = pd.DatetimeIndex(q.time.values)
years = dates.year + (dates.month >= 10)
rows = []
for gauge, values in zip(q.gauge_id.values, q.values, strict=True):
    s = pd.Series(values.astype(float), index=dates)
    annual = []
    for year in sorted(set(years)):
        a = s[years == year]
        if a.notna().mean() >= .7:
            ex = FlowExtremes(a)
            annual.append([ex.analyze_high_flows()['high_flow_avg_duration'], ex.analyze_low_flows()['low_flow_avg_duration']])
    means = np.mean(annual, axis=0)
    rows.append([str(gauge),*means,FlowVariability(s).calculate_flashiness_index()['flashiness_index']])
check = pd.DataFrame(rows,columns=['gauge_id','high_flow_dur','low_flow_dur','flashiness_index']).set_index('gauge_id')
for name in check:
    # CSV was serialized with float_format='%.6g'; compare at its exact precision.
    rounded = check[name].map(lambda x: float(f'{x:.6g}'))
    same = np.isclose(rounded,sig[name],rtol=0,atol=1e-12,equal_nan=True)
    print(name, 'rows=',len(same),'matching=',int(same.sum()),'max_raw_abs_difference=',float((check[name]-sig[name]).abs().max()),flush=True)
    assert same.all(), check.loc[~same,[name]].join(sig.loc[~same,[name]],rsuffix='_released').head()
print('PASS: all 1729 released rows match current date-contiguous event durations and pooled flashiness at CSV precision; no BFI or regenerated products.')
