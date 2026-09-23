# Hexagon figure data

These eleven JSON files document the six current hexagon maps: Figure 1,
Figure 5, and Figures B1–B4. Figure 3 displays individual gauges and has no
hexagon aggregation.

Each file records the projected grid, origin, radius, boundary-assignment rule,
reducer, cell values, total/valid/missing counts, and gauge-to-cell membership.
Climate categories use the displayed class mode; continuous fields use the
median of finite values. Empty cells are omitted. Values summarize sampled
outlets, not area-weighted conditions throughout a cell; nested gauges remain
dependent. Histograms count gauges rather than cells.

The calculation is implemented in `src/plots/hex_maps.py` and described in
manuscript Section 2.4. The network, precipitation, and signature generators
listed in `paper/README.md` update these JSONs when run with `--write`. CSV
companions are redundant local exports; the JSONs contain the complete support.
