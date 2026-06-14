# Large-sample hydrology dataset papers for CAMELS-RU

This folder stores paper PDFs and citation metadata only. Dataset archives are intentionally not downloaded here because CAMELS-RU has its own prepared dataset.

## Retrieved paper PDFs

### 2021 — LamaH-CE: LArge-SaMple DAta for Hydrology and Environmental Sciences for Central Europe

- Tier: `large_sample_dataset_descriptor`
- Region/scope: Central Europe / Upper Danube
- Journal/status: Earth System Science Data
- Authors: Klingler, Schulz, and Herrnegger
- DOI: https://doi.org/10.5194/essd-13-4529-2021
- Article: https://essd.copernicus.org/articles/13/4529/2021/
- PDF: `docs/literature/large_sample_hydrology_papers/klingler_2021_lamah_ce_essd.pdf` (16.5 MB)
- BibTeX: `docs/literature/large_sample_hydrology_papers/klingler_2021_lamah_ce_essd.bib`
- SHA256: `9e0d5146be0f34656f0edbc61955432f2fb63d285156f2b2e40a0d4c7033bfa0`
- Notes: Relevant non-CAMELS large-sample dataset descriptor; useful for metadata classes, uncertainty/limitations language, and baseline model plausibility checks.

## Tracked but no paper PDF found

### 2026 — CAMELS-PE: Hydrometeorological time series and catchment attributes for 136 catchments in Peru

- Region/scope: Peru
- Status: Earth System Science Data, in preparation
- DOI: not available yet
- Reference page: https://hllauca.github.io/RCamelsPE/index.html
- Secondary page: https://www.gob.pe/institucion/senamhi/noticias/1403342-camels-pe-informacion-abierta-para-comprender-mejor-el-agua-en-el-peru
- Dataset DOI recorded for provenance only, not downloaded: https://doi.org/10.5281/zenodo.20058779
- Notes: Official/R package pages cite an ESSD manuscript in preparation; no paper PDF found as of retrieval. Dataset DOI is recorded only as provenance and must not be downloaded by this script.

### 2025 — Development of CAMELS-Nordic, a large-scale hydrometeorological and catchment properties dataset for Norway and Sweden

- Region/scope: Norway and Sweden
- Status: EGU General Assembly 2025 abstract
- DOI: https://doi.org/10.5194/egusphere-egu25-10411
- Reference page: https://meetingorganizer.copernicus.org/EGU25/EGU25-10411.html

- Notes: Conference abstract only; no full paper PDF found. Track for future ESSD/HESS paper search.

## CAMELS-RU implications to check

- Keep our paper focused on a reproducible dataset descriptor: source ledger, catchment inclusion/exclusion rules, variables, units, temporal coverage, coordinate reference systems, and data-access statement.
- Add explicit limitations/uncertainty language: gauge quality/completeness, human regulation, forcing bias, missingness, snow/cold-region processes, elevation effects, and spatial representativeness.
- Provide benchmark/plausibility diagnostics, not just files: hydrological signatures, water balance checks, regime maps, forcing comparisons, and baseline model or signature sanity checks where feasible.
- Consider a topology-aware section inspired by LaMAH: independent/intermediate catchments, upstream areas, river network links, gauge IDs, and whether CAMELS-RU supports network-aware experiments.
- Make the dynamic-update story explicit: CAMELS-Nordic emphasizes Python tools to update time series automatically; CAMELS-RU should state whether updates are scripted, versioned, and reproducible.
- Maintain a comparison matrix against CAMELS-FR/DK/GB/COL/CL, Caravan, CAMELS-PE, CAMELS-Nordic, and LaMAH-CE so reviewer-facing claims are grounded in existing dataset-paper conventions.

## Combined files

- Metadata JSON: `docs/literature/large_sample_hydrology_papers/metadata.json`
- Combined BibTeX: `docs/literature/large_sample_hydrology_papers/large_sample_hydrology_papers.bib`

<!-- one-time-camels-reference-expansion:start -->

## One-time CAMELS reference expansion

Additional open-access paper PDFs retrieved for CAMELS-RU reference work. Dataset archives were not downloaded.

### 2023 — Caravan — A global community dataset for large-sample hydrology

- Tier: `global_large_sample_dataset_descriptor`
- Region/scope: Global / Caravan
- Journal/status: Scientific Data
- DOI: https://doi.org/10.1038/s41597-023-01975-w
- Article: https://www.nature.com/articles/s41597-023-01975-w
- PDF: `docs/literature/large_sample_hydrology_papers/kratzert_2023_caravan_scidata.pdf` (2.3 MB)
- BibTeX: `docs/literature/large_sample_hydrology_papers/kratzert_2023_caravan_scidata.bib`
- SHA256: `e899591a930b44a35131633dc3c20387bf137a54a1e02db83f4b05662f257a56`
- Notes: Global community dataset descriptor; important contrast for CAMELS-RU because Caravan excludes Russian gauges.

### 2024 — EStreams: An integrated dataset and catalogue of streamflow, hydro-climatic variables and landscape descriptors for Europe

- Tier: `continental_large_sample_dataset_descriptor`
- Region/scope: Europe / EStreams
- Journal/status: Scientific Data
- DOI: https://doi.org/10.1038/s41597-024-03706-1
- Article: https://www.nature.com/articles/s41597-024-03706-1
- PDF: `docs/literature/large_sample_hydrology_papers/do_nascimento_2024_estreams_scidata.pdf` (4.8 MB)
- BibTeX: `docs/literature/large_sample_hydrology_papers/do_nascimento_2024_estreams_scidata.bib`
- SHA256: `0f2857ec7d56ab6eb7be9594fd6dcabefaa7c82126af3fbc866b175ab898db49`
- Notes: Continental large-sample dataset descriptor; relevant comparator for catalogue structure and forcing-variable reporting.

### 2025 — CAMELSH: A Large-Sample Hourly Hydrometeorological Dataset and Attributes at Watershed-Scale for CONUS

- Tier: `camels_extension_hourly`
- Region/scope: United States / CONUS hourly
- Journal/status: Scientific Data
- DOI: https://doi.org/10.1038/s41597-025-05612-6
- Article: https://www.nature.com/articles/s41597-025-05612-6
- PDF: `docs/literature/large_sample_hydrology_papers/tran_2025_camelsh_scidata.pdf` (8.3 MB)
- BibTeX: `docs/literature/large_sample_hydrology_papers/tran_2025_camelsh_scidata.bib`
- SHA256: `9bfe856285283d5378360e495e1e11b3c016ad0c650f819683eb7908cf4e88da`
- Notes: Hourly CAMELS-family extension; useful for temporal-resolution and high-frequency-data discussion.

### 2025 — Swiss data quality: augmenting CAMELS-CH with isotopes, water quality, agricultural and atmospheric data

- Tier: `camels_extension_quality_isotopes`
- Region/scope: Switzerland
- Journal/status: Scientific Data
- DOI: https://doi.org/10.1038/s41597-025-05625-1
- Article: https://www.nature.com/articles/s41597-025-05625-1
- PDF: `docs/literature/large_sample_hydrology_papers/do_nascimento_2025_camels_ch_quality_scidata.pdf` (3.7 MB)
- BibTeX: `docs/literature/large_sample_hydrology_papers/do_nascimento_2025_camels_ch_quality_scidata.bib`
- SHA256: `f8357fa45088950dc57386dec6e66414a6d1260aa46d211e9219f1cf3185828e`
- Notes: CAMELS-CH augmentation paper; useful for extension/augmentation framing and data-quality metadata.

<!-- one-time-camels-reference-expansion:end -->
