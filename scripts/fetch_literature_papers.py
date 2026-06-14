#!/usr/bin/env python3
"""Fetch paper PDFs/BibTeX for CAMELS-RU literature review.

Scope guard: this script downloads *paper PDFs only* plus small citation metadata.
It intentionally refuses dataset/archive URLs (Zenodo records, .zip, .tar, etc.).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import textwrap
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "literature" / "large_sample_hydrology_papers"
USER_AGENT = "camels-ru-literature-fetcher/1.0 (+paper-pdfs-only)"

TARGETS: list[dict[str, Any]] = [
    {
        "key": "klingler_2021_lamah_ce_essd",
        "tier": "large_sample_dataset_descriptor",
        "region": "Central Europe / Upper Danube",
        "title": "LamaH-CE: LArge-SaMple DAta for Hydrology and Environmental Sciences for Central Europe",
        "authors_short": "Klingler, Schulz, and Herrnegger",
        "year": "2021",
        "journal": "Earth System Science Data",
        "doi": "10.5194/essd-13-4529-2021",
        "article_url": "https://essd.copernicus.org/articles/13/4529/2021/",
        "pdf_url": "https://essd.copernicus.org/articles/13/4529/2021/essd-13-4529-2021.pdf",
        "bib_url": "https://essd.copernicus.org/articles/13/4529/2021/essd-13-4529-2021.bib",
        "notes": "Relevant non-CAMELS large-sample dataset descriptor; useful for metadata classes, uncertainty/limitations language, and baseline model plausibility checks.",
    },
    {
        "key": "llauca_2026_camels_pe_in_preparation",
        "tier": "pending_dataset_descriptor",
        "region": "Peru",
        "title": "CAMELS-PE: Hydrometeorological time series and catchment attributes for 136 catchments in Peru",
        "authors_short": "Llauca et al.",
        "year": "2026",
        "journal": "Earth System Science Data, in preparation",
        "doi": "",
        "article_url": "https://hllauca.github.io/RCamelsPE/index.html",
        "secondary_url": "https://www.gob.pe/institucion/senamhi/noticias/1403342-camels-pe-informacion-abierta-para-comprender-mejor-el-agua-en-el-peru",
        "dataset_doi": "10.5281/zenodo.20058779",
        "pdf_url": "",
        "bib_url": "",
        "notes": "Official/R package pages cite an ESSD manuscript in preparation; no paper PDF found as of retrieval. Dataset DOI is recorded only as provenance and must not be downloaded by this script.",
    },
    {
        "key": "valseth_2025_camels_nordic_egu",
        "tier": "conference_abstract_pending_descriptor",
        "region": "Norway and Sweden",
        "title": "Development of CAMELS-Nordic, a large-scale hydrometeorological and catchment properties dataset for Norway and Sweden",
        "authors_short": "Valseth et al.",
        "year": "2025",
        "journal": "EGU General Assembly 2025 abstract",
        "doi": "10.5194/egusphere-egu25-10411",
        "article_url": "https://meetingorganizer.copernicus.org/EGU25/EGU25-10411.html",
        "pdf_url": "",
        "bib_url": "",
        "notes": "Conference abstract only; no full paper PDF found. Track for future ESSD/HESS paper search.",
    },
]

BLOCKED_DOWNLOAD_PATTERNS = re.compile(r"(zenodo\.org/(records|api/records)|\.zip($|[?#])|\.tar($|[?#])|\.tgz($|[?#])|\.nc($|[?#])|\.csv($|[?#]))", re.I)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def ensure_paper_pdf_url(url: str) -> None:
    if not url:
        return
    if BLOCKED_DOWNLOAD_PATTERNS.search(url):
        raise ValueError(f"Refusing non-paper/dataset-like URL: {url}")
    if ".pdf" not in url.lower():
        raise ValueError(f"PDF URL must explicitly point to a .pdf paper: {url}")


def ensure_paper_bib_url(url: str) -> None:
    if not url:
        return
    if BLOCKED_DOWNLOAD_PATTERNS.search(url):
        raise ValueError(f"Refusing non-paper/dataset-like BibTeX URL: {url}")
    if ".bib" not in url.lower():
        raise ValueError(f"BibTeX URL must explicitly point to a .bib citation file: {url}")


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def download_target(target: dict[str, Any], force: bool = False) -> dict[str, Any]:
    record = dict(target)
    key = target["key"]
    pdf_url = target.get("pdf_url") or ""
    bib_url = target.get("bib_url") or ""

    if pdf_url:
        ensure_paper_pdf_url(pdf_url)
        pdf_path = OUT_DIR / f"{key}.pdf"
        if force or not pdf_path.exists():
            data = fetch(pdf_url)
            if not data.startswith(b"%PDF-"):
                raise ValueError(f"Downloaded file is not a PDF: {pdf_url}")
            pdf_path.write_bytes(data)
        else:
            data = pdf_path.read_bytes()
        record["pdf_file"] = str(pdf_path.relative_to(ROOT))
        record["pdf_bytes"] = len(data)
        record["pdf_sha256"] = sha256_bytes(data)
        record["pdf_status"] = "downloaded"
    else:
        record["pdf_status"] = "not_available"
        record["pdf_file"] = ""

    if bib_url:
        ensure_paper_bib_url(bib_url)
        # BibTeX citation metadata is allowed; dataset/archive downloads remain blocked above.
        bib_path = OUT_DIR / f"{key}.bib"
        if force or not bib_path.exists():
            bib = fetch(bib_url).decode("utf-8", "replace")
            bib_path.write_text(bib, encoding="utf-8")
        record["bib_file"] = str(bib_path.relative_to(ROOT))
    else:
        record["bib_file"] = ""

    return record


def write_indexes(records: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "metadata.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    bibs = []
    for rec in records:
        bib_file = rec.get("bib_file")
        if bib_file:
            bibs.append((ROOT / bib_file).read_text(encoding="utf-8"))
    (OUT_DIR / "large_sample_hydrology_papers.bib").write_text("\n\n".join(bibs).strip() + ("\n" if bibs else ""), encoding="utf-8")

    lines = [
        "# Large-sample hydrology dataset papers for CAMELS-RU",
        "",
        "This folder stores paper PDFs and citation metadata only. Dataset archives are intentionally not downloaded here because CAMELS-RU has its own prepared dataset.",
        "",
        "## Retrieved paper PDFs",
        "",
    ]
    downloaded = [r for r in records if r.get("pdf_status") == "downloaded"]
    if not downloaded:
        lines.append("- None.")
    for rec in downloaded:
        mb = rec.get("pdf_bytes", 0) / 1_000_000
        lines.extend([
            f"### {rec['year']} — {rec['title']}",
            "",
            f"- Tier: `{rec['tier']}`",
            f"- Region/scope: {rec['region']}",
            f"- Journal/status: {rec['journal']}",
            f"- Authors: {rec['authors_short']}",
            f"- DOI: https://doi.org/{rec['doi']}" if rec.get("doi") else "- DOI: not available yet",
            f"- Article: {rec['article_url']}",
            f"- PDF: `{rec['pdf_file']}` ({mb:.1f} MB)",
            f"- BibTeX: `{rec['bib_file']}`" if rec.get("bib_file") else "- BibTeX: not available",
            f"- SHA256: `{rec['pdf_sha256']}`",
            f"- Notes: {rec['notes']}",
            "",
        ])

    pending = [r for r in records if r.get("pdf_status") != "downloaded"]
    lines.extend(["## Tracked but no paper PDF found", ""])
    for rec in pending:
        lines.extend([
            f"### {rec['year']} — {rec['title']}",
            "",
            f"- Region/scope: {rec['region']}",
            f"- Status: {rec['journal']}",
            f"- DOI: https://doi.org/{rec['doi']}" if rec.get("doi") else "- DOI: not available yet",
            f"- Reference page: {rec['article_url']}",
            f"- Secondary page: {rec['secondary_url']}" if rec.get("secondary_url") else "",
            f"- Dataset DOI recorded for provenance only, not downloaded: https://doi.org/{rec['dataset_doi']}" if rec.get("dataset_doi") else "",
            f"- Notes: {rec['notes']}",
            "",
        ])
    lines.extend([
        "## CAMELS-RU implications to check",
        "",
        "- Keep our paper focused on a reproducible dataset descriptor: source ledger, catchment inclusion/exclusion rules, variables, units, temporal coverage, coordinate reference systems, and data-access statement.",
        "- Add explicit limitations/uncertainty language: gauge quality/completeness, human regulation, forcing bias, missingness, snow/cold-region processes, elevation effects, and spatial representativeness.",
        "- Provide benchmark/plausibility diagnostics, not just files: hydrological signatures, water balance checks, regime maps, forcing comparisons, and baseline model or signature sanity checks where feasible.",
        "- Consider a topology-aware section inspired by LaMAH: independent/intermediate catchments, upstream areas, river network links, gauge IDs, and whether CAMELS-RU supports network-aware experiments.",
        "- Make the dynamic-update story explicit: CAMELS-Nordic emphasizes Python tools to update time series automatically; CAMELS-RU should state whether updates are scripted, versioned, and reproducible.",
        "- Maintain a comparison matrix against CAMELS-FR/DK/GB/COL/CL, Caravan, CAMELS-PE, CAMELS-Nordic, and LaMAH-CE so reviewer-facing claims are grounded in existing dataset-paper conventions.",
        "",
        "## Combined files",
        "",
        "- Metadata JSON: `docs/literature/large_sample_hydrology_papers/metadata.json`",
        "- Combined BibTeX: `docs/literature/large_sample_hydrology_papers/large_sample_hydrology_papers.bib`",
        "",
    ])
    # Drop intentionally empty optional lines and collapse repeated blank lines.
    cleaned = []
    last_blank = False
    for line in lines:
        if line.strip():
            cleaned.append(line)
            last_blank = False
        elif not last_blank:
            cleaned.append("")
            last_blank = True
    (OUT_DIR / "README.md").write_text("\n".join(cleaned).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch paper PDFs only for CAMELS-RU literature review")
    parser.add_argument("--force", action="store_true", help="re-download existing PDFs/BibTeX")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for target in TARGETS:
        print(f"Processing {target['key']} ...", file=sys.stderr)
        records.append(download_target(target, force=args.force))
    write_indexes(records)
    print(json.dumps({"out_dir": str(OUT_DIR.relative_to(ROOT)), "records": len(records)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
