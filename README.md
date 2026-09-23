# CAMELS-RU

[![Code license: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)

Processing code, scientific analyses, and manuscript assets for a hydroclimatic
dataset of **3,353 Russian catchments**, covering 2008–2023. The data-description
manuscript is being prepared for *Earth System Science Data* (ESSD).

## Dataset

| Component | Coverage |
|---|---|
| Catchments | 3,353 manually inspected boundaries; 3,011 have reference areas |
| Discharge | 2,170 gauges; 2,065 graded, including 936 strict Grade A |
| Water level | 2,989 gauges |
| Primary forcing | MSWEP v2.8 precipitation, ERA5-Land temperature, GLEAM4 potential evapotranspiration |
| Attributes | 281 HydroATLAS source fields plus 7 derived fields; 3,339 catchments |
| Signatures | 16 signatures plus 3 precipitation-product variants; 1,729 rows, of which 1,716 are non-anomalous |

Grades are conditional screening diagnostics, not independent measurements of
observational accuracy. A gauge is strict Grade A only when **every assessed year**
is Grade A. The release-default configuration evaluates 16 of the 21 defined flag
types. Coverage, interpolation provenance, and application-specific checks remain
necessary regardless of grade.

## Data access and release status

Data files are not stored in Git. The reserved dataset identifier is
[10.5281/zenodo.22132299](https://doi.org/10.5281/zenodo.22132299); anonymous access
and uploaded-file parity have not yet been verified for submission. This README
does not announce a public release or a publication date.

The frozen numerical baseline is `CAMELS_RU_v1.0`. A separate, unpublished
`CAMELS_RU_v1.1_cf19` candidate adds station coordinates and metadata while
preserving the existing numerical values. Its three NetCDF files pass strict
CF-1.9 checks. See the [validation record](paper/metadata/VALIDATION.md),
[candidate README](paper/metadata/README_v1.1_cf19.md), and
[changelog](paper/metadata/CHANGELOG_v1.1_cf19.md).

For reuse, consult:

- [Signature crosswalk](paper/metadata/signature_crosswalk.json): definitions,
  thresholds, annual aggregation, missing-date handling, and qualified comparisons
  with other CAMELS datasets. Names alone do not establish equivalence.
- [Attribute metadata](paper/metadata/hydroatlas_metadata.json): units and spatial
  support, including eleven invalid categorical-code means (`*_smj`) that must be
  excluded from analysis. The other fields retain their documented qualifications.
- [Loading example](examples/load_camels_ru.py): supports both `gauge_id` and
  `station` NetCDF dimensions and uses the metadata above.

## Installation and checks

Install [pixi](https://pixi.sh), then:

```bash
git clone https://github.com/HydroInformaticsRu/camels_ru.git
cd camels_ru
pixi install
pixi run lint
for t in tests/test_*.py; do pixi run python "$t" || exit 1; done
```

The tests use synthetic inputs and retained small scientific audit tables; they do
not require executing notebooks or rebuilding the dataset. Processing scripts have
separate input requirements, documented in their command-line help and source.
Raw source products and the locally configured `data/` directory are not included.

Once the baseline package is available under `release/CAMELS_RU_v1.0/`:

```bash
pixi run python examples/load_camels_ru.py release/CAMELS_RU_v1.0
pixi run python scripts/verify_macros.py --release-dir release/CAMELS_RU_v1.0
```

The macro check also needs the manuscript submodule; see [paper/README.md](paper/README.md).

## Repository structure

| Path | Contents |
|---|---|
| `src/` | Parsing, geospatial processing, forcing aggregation, grading, signatures, and plotting modules |
| `scripts/` | Processing, verification, and figure-generation entry points |
| `notebooks/` | Analysis notebooks and paired Python sources |
| `tests/` | Self-checking regression scripts used by CI |
| `examples/` | Dataset-loading example |
| `app/` | Local web application for inspecting records |
| `paper/overleaf/` | Canonical manuscript, as an Overleaf Git submodule |
| `paper/images/`, `paper/figures_src/` | Manuscript figures and workflow-diagram source |
| `paper/figure_data/` | Machine-readable support for plotted hexagon summaries |
| `paper/tables/`, `results/hess_quality/` | Small scientific tables used by the manuscript and numerical verifier |
| `paper/metadata/` | Release metadata, crosswalks, and validation documentation |

Large data packages, environment caches, generated previews, internal editorial
reviews, and personal agent/editor settings are excluded from the tracked tree.
The manuscript bibliography is maintained in `paper/overleaf/refs.bib`.

## Citation and licensing

Use [CITATION.cff](CITATION.cff) for code citation metadata. The associated ESSD
manuscript is in preparation; it is not presented here as an accepted publication.

Processing code is distributed under the [MIT license](LICENSE). The existing
dataset documentation states CC BY 4.0; the source-observation redistribution basis
and final dataset licensing statement remain to be documented before publication.
Upstream products retain their respective terms.

The work uses observations from Roshydromet/AIS GMVO and products from MERIT Hydro,
HydroATLAS, MSWEP, ERA5-Land, and GLEAM4. Product references and processing methods
are given in the manuscript and release metadata.

Contact: Dmitrii V. Abramov — dmbrmv@icloud.com.
