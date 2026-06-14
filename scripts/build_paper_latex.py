"""Legacy converter: regenerate paper/latex/sections/*.tex from paper/manuscript.md.

The canonical collaborative manuscript is paper/overleaf/. This script is kept
only for archaeology of the Markdown-era workflow and refuses to run unless
CAMELS_RU_LEGACY_MD_BUILD=1 is set.

Pipeline:
  1. Split manuscript.md into sections by ``## N Title`` headings.
  2. Run pandoc MD → LaTeX per section.
  3. Post-process each output:
     a. Wrap figure blocks: ``![Figure N](path)`` + caption paragraph → figure env.
     b. Insert \\label{sec:*} after \\section{} and \\subsection{}.
     c. Replace hardcoded numbers with \\macros where safe.
     d. Convert narrative citations "(Author et al., Year)" → \\citep{Key}
        using a map harvested from refs.bib first-author + year.
     e. Strip pandoc-specific wrappers (\\pandocbounded, horizontal rules).
     f. Convert "Sect.~N" and "Figure~N" text refs to \\ref{} where possible.
  4. Write each section file.

Run: pixi run python scripts/build_paper_latex.py
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys
import unicodedata


def _ascii_fold(name: str) -> str:
    """Fold Unicode (Muñoz → Munoz, Höge → Hoge) for citation matching."""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return folded


REPO = Path(__file__).resolve().parents[1]
MD = REPO / "paper" / "manuscript.md"
SECTIONS_OUT = REPO / "paper" / "latex" / "sections"
BIB = REPO / "paper" / "latex" / "refs.bib"
TMP = REPO / ".tmp" / "build_paper"


# Section title → (output filename, \\label name, include heading in output?)
SECTION_MAP: list[tuple[str, str, str | None, bool]] = [
    ("## Abstract", "00_abstract.tex", None, False),
    ("## 1 Introduction", "01_introduction.tex", "sec:introduction", True),
    ("## 2 Study Area", "02_study_area.tex", "sec:study_area", True),
    ("## 3 Data Sources and Methods", "03_data_methods.tex", "sec:data_methods", True),
    ("## 4 Technical Validation", "04_technical_validation.tex", "sec:technical_validation", True),
    ("## 5 Data Records", "05_data_records.tex", "sec:data_records", True),
    ("## 6 Conclusions", "06_conclusions.tex", "sec:conclusions", True),
]

# Subsection label mapping (from existing LaTeX — preserve cross-ref targets)
SUBSECTION_LABELS = {
    "Inter-Dataset Correlations": "sec:precip_intercomparison",
    "Water Balance Consistency": "sec:water_balance",
    "Budyko Consistency Check and ET Adequacy": "sec:budyko",
    "Precipitation--Discharge Relationship": "sec:precip_discharge",
    "Discharge Quality Control": "sec:discharge_qc",
    "Consistency Cross-Check Against GRDC Re-Exports": "sec:grdc_crosscheck",
    "Watershed Boundary Accuracy": "sec:boundary_accuracy",
    "Dataset Composition": "sec:composition",
    "Dataset Structure": "sec:structure",
    "Usage Notes": "sec:usage_notes",
    "Limitations": "sec:limitations",
    "Future Updates": "sec:future_updates",
    "GLEAM Potential Evapotranspiration": "sec:gleam_pet",
    "Hydrological Signatures": "sec:signatures",
}

# Literal-string → macro. Applied outside of \\cite{} and \\includegraphics{}.
# Order: longer patterns before shorter to avoid partial matches.
MACRO_MAP: list[tuple[str, str]] = [
    ("3,353", r"\ntotal"),
    ("2,989", r"\nwaterlevel"),
    ("2,170", r"\ndischarge"),
    ("2,067", r"\ngraded"),
    ("1,845", r"\nsigngauges"),
    ("1,804", r"\nwaterbalgauges"),
    ("1,716", r"\nsigngaugesstrict"),
    ("1,643", r"\nhalfflowgauges"),
    ("1,641", r"\nhalfflowstrict"),
    ("2008--2023", r"\years"),
    ("2008-2023", r"\years"),
    ("CC BY 4.0", r"\license"),
]

# Figure filename (stem) → \\label name
FIG_LABELS = {
    "fig_gauge_network": "fig:gauge_network",
    "fig_quality_assessment": "fig:quality_assessment",
    "fig_hydro_characteristics": "fig:hydro_characteristics",
    "fig_precip_comparison": "fig:precip_comparison",
    "fig_forcing_correlations": "fig:forcing_correlations",
    "fig_water_balance": "fig:water_balance",
    "fig_budyko": "fig:budyko",
    "fig_hydro_signatures_1": "fig:hydro_signatures_1",
    "fig_hydro_signatures_2": "fig:hydro_signatures_2",
}

# Table number in MD → tables/file (replaces pandoc longtable output with \\input)
TABLE_MAP = {
    "1": "camels_comparison",
    "2": "hydroatlas_attributes",
    "3": "hydro_signatures",
    "4": "dataset_files",
}

# Text-reference mapping: "Table N" → \\ref{tab:X}, "Figure N" → \\ref{fig:X}
TABLE_REF_MAP = {
    "1": "tab:camels_comparison",
    "2": "tab:hydroatlas_attributes",
    "3": "tab:hydro_signatures",
    "4": "tab:dataset_files",
}
FIGURE_REF_MAP = {
    "1": "fig:gauge_network",
    "2": "fig:quality_assessment",
    "3": "fig:hydro_characteristics",
    "4": "fig:precip_comparison",
    "5": "fig:forcing_correlations",
    "6": "fig:water_balance",
    "7": "fig:budyko",
    "8": "fig:hydro_signatures_1",
    "9": "fig:hydro_signatures_2",
}


def _extract_braced_field(body: str, field: str) -> str | None:
    """Extract a BibTeX field value, handling nested braces (e.g. \\~{n})."""
    m = re.search(rf"{field}\s*=\s*(\{{|\")", body)
    if not m:
        return None
    start = m.end()
    opener = m.group(1)
    if opener == '"':
        # Quoted string — find matching unescaped "
        end_m = re.search(r'(?<!\\)"', body[start:])
        return body[start : start + end_m.start()] if end_m else None
    # Braced — count depth
    depth = 1
    i = start
    while i < len(body) and depth:
        ch = body[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return body[start:i]
        i += 1
    return None


def parse_bib_authors() -> dict[str, str]:
    """Build a map (first_author_lastname, year) → bibkey from refs.bib.

    Returns keys as "Lastname_Year" tuples encoded as strings.
    """
    text = BIB.read_text()
    entries = re.findall(r"@\w+\{([^,]+),(.*?)\n\}", text, flags=re.DOTALL)
    mapping: dict[str, str] = {}
    for key, body in entries:
        key = key.strip()
        author_raw = _extract_braced_field(body, "author")
        year_raw = _extract_braced_field(body, "year")
        if not author_raw or not year_raw:
            continue
        year_m = re.match(r"(\d{4})", year_raw.strip())
        if not year_m:
            continue
        year = year_m.group(1)
        # First author lastname. Format is typically "Lastname, First and Next, First..."
        first_author = author_raw.split(" and ")[0].strip()
        if "," in first_author:
            lastname = first_author.split(",")[0].strip()
        else:
            # "First Lastname" form
            parts = first_author.split()
            lastname = parts[-1] if parts else first_author
        # Strip LaTeX accents in all common forms:
        #   {\"o}, {\'e}, {\~n}   (outer-braced command)
        #   \"{o}, \'{e}, \~{n}   (command with braced arg)
        #   \"o,  \'e,  \~n       (command without braces)
        lastname = re.sub(r"\{\\[`\"'^~=\.][{]?([a-zA-Z])[}]?\}", r"\1", lastname)
        lastname = re.sub(r"\\[`\"'^~=\.]\{([a-zA-Z])\}", r"\1", lastname)
        lastname = re.sub(r"\\[`\"'^~=\.]([a-zA-Z])", r"\1", lastname)
        lastname = re.sub(r"[{}\\]", "", lastname)
        # Compound surnames: "Munoz-Sabater" → store both full and first component
        folded = _ascii_fold(lastname)
        mapping[f"{folded}_{year}"] = key
        if "-" in folded:
            mapping[f"{folded.split('-')[0]}_{year}"] = key
    return mapping


def split_manuscript() -> dict[str, str]:
    """Split MD into sections keyed by the section heading."""
    text = MD.read_text()
    # Build a list of (heading, start_offset) tuples
    heading_re = re.compile(r"^## [^\n]+$", re.MULTILINE)
    headings = [(m.group(), m.start()) for m in heading_re.finditer(text)]
    sections: dict[str, str] = {}
    for i, (h, start) in enumerate(headings):
        end = headings[i + 1][1] if i + 1 < len(headings) else len(text)
        sections[h] = text[start:end]
    return sections


def run_pandoc(md_text: str) -> str:
    """Run pandoc MD → LaTeX and return the raw output."""
    TMP.mkdir(parents=True, exist_ok=True)
    tmp_in = TMP / "in.md"
    tmp_in.write_text(md_text)
    result = subprocess.run(
        [
            "pandoc",
            "--from",
            "markdown",
            "--to",
            "latex",
            "--wrap=preserve",
            "--top-level-division=section",
            "--shift-heading-level-by=-1",
            str(tmp_in),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# Unicode characters that pdflatex (utf8 inputenc) cannot render directly.
# Replacement strings are LaTeX code (math or text) safe in running prose.
UNICODE_TO_LATEX = {
    "≤": r"$\leq$",
    "≥": r"$\geq$",
    "≈": r"$\approx$",
    "×": r"$\times$",
    "÷": r"$\div$",
    "±": r"$\pm$",
    "→": r"$\to$",
    "⇒": r"$\Rightarrow$",
    "∑": r"$\sum$",
    "∫": r"$\int$",
    "∞": r"$\infty$",
    "…": r"\ldots{}",
    "•": r"\textbullet{}",
    "°": r"$^\circ$",
    "²": r"$^2$",
    "³": r"$^3$",
    "¹": r"$^1$",
    "⁻¹": r"$^{-1}$",
    "⁻²": r"$^{-2}$",
    "⁻": r"$^{-}$",  # bare superscript minus
    "−": "-",  # Unicode minus (U+2212) → ASCII hyphen
    # Subscripts (used in equations rendered as text, e.g. Q_{33})
    "₀": r"$_0$",
    "₁": r"$_1$",
    "₂": r"$_2$",
    "₃": r"$_3$",
    "₄": r"$_4$",
    "₅": r"$_5$",
    "₆": r"$_6$",
    "₇": r"$_7$",
    "₈": r"$_8$",
    "₉": r"$_9$",
    "₋": r"$_-$",
    "ᵢ": r"$_i$",
    "ₚ": r"$_p$",
    "Σ": r"$\Sigma$",
    "½": r"$\tfrac{1}{2}$",
    "–": "--",
    "—": "---",
    "α": r"$\alpha$",
    "β": r"$\beta$",
    "γ": r"$\gamma$",
    "Δ": r"$\Delta$",
    "δ": r"$\delta$",
    "λ": r"$\lambda$",
    "μ": r"$\mu$",
    "π": r"$\pi$",
    "σ": r"$\sigma$",
    "τ": r"$\tau$",
    "φ": r"$\varphi$",
    "ω": r"$\omega$",
}


def substitute_unicode_math(tex: str) -> str:
    """Replace Unicode math/special chars that pdflatex can't handle.

    Operates line-wise and skips substitution inside image paths
    (\\includegraphics{...}) and labels/refs where special chars shouldn't
    appear anyway. Accented Latin letters (ñ, ö, etc.) are left alone because
    inputenc-utf8 handles them.
    """
    # Sort by key length (longest first) so multi-char sequences like "⁻¹" are
    # replaced before their parts "⁻" and "¹".
    for ch, repl in sorted(UNICODE_TO_LATEX.items(), key=lambda kv: -len(kv[0])):
        tex = tex.replace(ch, repl)
    # Coalesce adjacent same-operator math groups — e.g. "$^{-}$$^1$" after
    # per-char replacement should become "$^{-1}$", not "$^{-}^1$".
    # Handles any mix of super-/sub-script tokens.
    for _ in range(5):
        tex = re.sub(
            r"\$\^\{([^{}]+)\}\$\$\^\{?([^{}$]+)\}?\$",
            lambda m: f"$^{{{m.group(1)}{m.group(2)}}}$",
            tex,
        )
        tex = re.sub(
            r"\$_\{?([^{}$]+)\}?\$\$_\{?([^{}$]+)\}?\$",
            lambda m: f"$_{{{m.group(1)}{m.group(2)}}}$",
            tex,
        )
    # "No counter 'none'" fix: pandoc longtable wrapper uses \def\LTcaptype{none}.
    # For unreplaced tables (Table 4 etc.) that leak past replace_tables(),
    # strip the wrapper — we don't need the caption-counter suppression.
    tex = re.sub(r"\{\\def\\LTcaptype\{none\}[^\n]*\n", "", tex)
    # The wrapper closing `}` appears alone on a line after `\end{longtable}`
    tex = re.sub(r"\\end\{longtable\}\s*\}", r"\\end{longtable}", tex)
    return tex


def strip_pandoc_wrappers(tex: str) -> str:
    """Remove pandoc-isms that don't fit a Copernicus paper."""
    # Horizontal rule → nothing (they're just MD separators)
    tex = re.sub(r"\\begin\{center\}\\rule\{[^}]+\}\{[^}]+\}\\end\{center\}", "", tex)
    # \pandocbounded{\includegraphics[...]{path}} → \includegraphics[width=\textwidth]{path}
    tex = re.sub(
        r"\\pandocbounded\{\\includegraphics\[[^\]]*\]\{([^}]+)\}\}",
        r"\\includegraphics[width=\\textwidth]{\1}",
        tex,
    )
    # Strip leading numbering from section headings: \section{1 Introduction} → \section{Introduction}
    tex = re.sub(
        r"\\(section|subsection|subsubsection)\{(\d+(?:\.\d+)*)\s+([^}]+)\}",
        r"\\\1{\3}",
        tex,
    )
    # Drop pandoc's auto-generated \label{introduction} — we add our own
    tex = re.sub(
        r"(\\(?:section|subsection|subsubsection)\{[^}]+\})\\label\{[a-z][a-z0-9\-]*\}",
        r"\1",
        tex,
    )
    # \textasciitilde17.1 (approximately) → $\sim$17.1
    tex = re.sub(r"\\textasciitilde(?=[\d\s])", r"$\\sim$", tex)
    # Unescape brackets pandoc escaped from literal MD brackets: {[}text{]} → [text]
    tex = re.sub(r"\{\[\}([^{}]*?)\{\]\}", r"[\1]", tex)
    # Trim triple blank lines anywhere
    return tex


def replace_tables(tex: str) -> str:
    """Replace pandoc-rendered longtables with \\input{tables/NAME.tex}.

    Matches the MD pattern ``**Table N.** caption\\n\\n{\\def\\LTcaptype...longtable...}``
    and replaces the whole block with \\input{tables/<mapped_name>.tex}.
    Tables without a mapping entry (e.g. Table 4 file structure) are left alone.
    """
    # Pattern spans from "\textbf{Table N.}" through the longtable group that follows,
    # plus any trailing "^†^ ..." footnote paragraph (pandoc renders this as a line
    # starting with \textsuperscript{†}). The hand-crafted \input table handles
    # its own footnotes via \begin{tablenotes}.
    # Pandoc emits two longtable variants:
    #   (a) simple cells → wrapped in {\def\LTcaptype{none} ... \end{longtable}}
    #   (b) wide/p-column cells → bare \begin{longtable}[...]{...} ... \end{longtable}
    # Accept both.
    pattern = re.compile(
        r"\\textbf\{Table\s+(?P<num>\d+)\.\}[^\n]*\n+"  # caption line
        r"(?:"
        r"\{\\def\\LTcaptype[\s\S]*?\\end\{longtable\}\s*\}"
        r"|"
        r"\\begin\{longtable\}[\s\S]*?\\end\{longtable\}"
        r")"
        r"(?:\s*\n+\\textsuperscript\{[^}]+\}[^\n]*(?:\n[^\n]+)*)?",
        re.MULTILINE,
    )

    def _repl(m: re.Match[str]) -> str:
        num = m.group("num")
        mapped = TABLE_MAP.get(num)
        if not mapped:
            return m.group(0)  # leave unmapped tables in place
        return f"\\input{{tables/{mapped}}}"

    return pattern.sub(_repl, tex)


def resolve_text_refs(tex: str) -> str:
    """Convert "Table N"/"Fig. N"/"Figure N"/"Sect. X.Y" text refs to \\ref{} / \\cref{}.

    Does NOT touch refs that already live inside \\caption{} (figure env) or table cells,
    since those are the target of references rather than referencing text.
    """

    # Replace "Table N" (captured group 1 = digit) → Table~\ref{tab:...}
    def _tab(m: re.Match[str]) -> str:
        n = m.group(1)
        ref = TABLE_REF_MAP.get(n)
        return f"Table~\\ref{{{ref}}}" if ref else m.group(0)

    tex = re.sub(r"\bTable\s+(\d+)\b", _tab, tex)

    # "Figure N" and "Fig.~N" / "Fig. N"
    def _fig(m: re.Match[str]) -> str:
        n = m.group(1)
        ref = FIGURE_REF_MAP.get(n)
        return f"Figure~\\ref{{{ref}}}" if ref else m.group(0)

    tex = re.sub(r"\b(?:Figure|Fig\.~?)\s+(\d+)\b", _fig, tex)

    # "Figures M and N" / "Figures M--N" / "Figures M and~N" → dual \ref
    def _figs(m: re.Match[str]) -> str:
        a, b = m.group(1), m.group(2)
        ra, rb = FIGURE_REF_MAP.get(a), FIGURE_REF_MAP.get(b)
        if ra and rb:
            return f"Figures~\\ref{{{ra}}} and~\\ref{{{rb}}}"
        return m.group(0)

    tex = re.sub(r"\bFigures\s+(\d+)(?:\s+and\s+|\s*--\s*)(\d+)\b", _figs, tex)
    return tex


def warn_unmatched_citations(tex: str, filename: str) -> list[str]:
    """Report any remaining "(Author et al., YYYY)" patterns not converted to \\citep{}."""
    remaining = re.findall(
        r"\(([A-ZÄÖÜÉÈÀÂÑÇÍÓÚÅØŁŽŠŘ][A-Za-zÀ-ÿ'\-]+"
        r"(?:\s+(?:et\s+al\.|and\s+[A-ZÄÖÜÉÈÀÂÑÇÍÓÚÅØŁŽŠŘ][A-Za-zÀ-ÿ'\-]+))?"
        r",?\s+\d{4}[a-z]?)\)",
        tex,
    )
    if remaining:
        print(f"  [warn] {filename}: unmatched citations: {remaining}")
    return remaining


def wrap_figures(tex: str) -> str:
    """Convert bare \\includegraphics + **Figure N.** caption → figure env."""
    # Pattern: \includegraphics[...]{path} ... \textbf{Figure N.} caption-until-blank-line
    pattern = re.compile(
        r"\\includegraphics\[[^\]]*\]\{(?P<path>[^}]+)\}\s*\n+"
        r"\\textbf\{Figure\s+(?P<num>\d+)\.\}\s*(?P<cap>.+?)"
        r"(?=\n\s*\n)",
        re.DOTALL,
    )

    def _repl(m: re.Match[str]) -> str:
        path = m.group("path")
        # Strip the images/ prefix — main.tex sets \graphicspath{{../images/}}
        path_stripped = path.split("/")[-1]
        cap = m.group("cap").strip()
        stem = Path(path).stem
        label = FIG_LABELS.get(stem, f"fig:{stem.replace('fig_', '')}")
        return (
            "\\begin{figure}[t]\n"
            "    \\centering\n"
            f"    \\includegraphics[width=\\textwidth]{{{path_stripped}}}\n"
            f"    \\caption{{{cap}}}\n"
            f"    \\label{{{label}}}\n"
            "\\end{figure}"
        )

    return pattern.sub(_repl, tex)


def apply_citation_map(tex: str, bib_map: dict[str, str]) -> str:
    """Convert narrative citations to \\citep{Key}.

    Handles:
      (Lastname et al., YYYY)        → ~\\citep{Key}
      (Lastname, YYYY)               → ~\\citep{Key}
      (Lastname et al., YYYY; ...)   → ~\\citep{Key1,Key2}
      Lastname et al. (YYYY)         → \\citet{Key}
    """
    # Unicode-friendly surname class: letters (incl. non-ASCII), hyphens, apostrophes
    SURNAME = r"([A-ZÄÖÜÉÈÀÂÑÇÍÓÚÅØŁŽŠŘ][A-Za-zÀ-ÿ'\-]+)"

    def _lookup(name: str, year: str) -> str | None:
        folded = _ascii_fold(name)
        return bib_map.get(f"{folded}_{year}") or bib_map.get(f"{folded.split('-')[0]}_{year}")

    # First: grouped citations with semicolons inside parens
    def _group_repl(m: re.Match[str]) -> str:
        body = m.group(1)
        parts = [p.strip() for p in body.split(";")]
        keys: list[str] = []
        for p in parts:
            mm = re.match(SURNAME + r"(?:\s+et\s+al\.)?,?\s+(\d{4})[a-z]?", p)
            if not mm:
                return m.group(0)
            key = _lookup(mm.group(1), mm.group(2))
            if not key:
                return m.group(0)
            keys.append(key)
        return f"~\\citep{{{','.join(keys)}}}"

    # Grouped citation: capture the full inner body for _group_repl
    tex = re.sub(
        r"\(((?:"
        + SURNAME
        + r"(?:\s+et\s+al\.)?,?\s+\d{4}[a-z]?"
        + r")(?:\s*;\s*"
        + SURNAME
        + r"(?:\s+et\s+al\.)?,?\s+\d{4}[a-z]?)+)\)",
        _group_repl,
        tex,
    )

    # Paren citation: (Lastname et al., YYYY) or (Lastname, YYYY)
    #                 or (Lastname and Lastname, YYYY)
    def _paren_repl(m: re.Match[str]) -> str:
        key = _lookup(m.group(1), m.group(2))
        if not key:
            return m.group(0)
        return f"~\\citep{{{key}}}"

    tex = re.sub(
        r"\(" + SURNAME + r"(?:\s+et\s+al\.|\s+and\s+" + SURNAME + r")?,?\s+(\d{4})[a-z]?\)",
        lambda m: (
            f"~\\citep{{{_lookup(m.group(1), m.group(m.lastindex))}}}"
            if _lookup(m.group(1), m.group(m.lastindex))
            else m.group(0)
        ),
        tex,
    )

    # Inline citation: "Lastname et al. (YYYY)" or "Lastname (YYYY)"
    # \citet{Key} already renders as "Lastname et al. (YYYY)" so we replace the
    # whole match (author + year) with just \citet{Key} — no prefix preserved.
    def _inline_repl(m: re.Match[str]) -> str:
        key = _lookup(m.group(1), m.group(2))
        if not key:
            return m.group(0)
        return f"\\citet{{{key}}}"

    # Allow non-breaking tilde between "et al." and "(year)" (pandoc inserts ~)
    tex = re.sub(
        SURNAME + r"(?:\s+et\s+al\.)?[\s~]+\((\d{4})[a-z]?\)",
        _inline_repl,
        tex,
    )

    # Semicolon-prefixed citations inside parens, mixed with descriptive text:
    #   (...; Surname, YYYY)  →  keep preceding text, append ~\citep{Key}
    def _semi_repl(m: re.Match[str]) -> str:
        key = _lookup(m.group(1), m.group(2))
        if not key:
            return m.group(0)
        return f"; \\citet{{{key}}}"

    tex = re.sub(
        r";\s*" + SURNAME + r"(?:\s+et\s+al\.)?,?\s+(\d{4})[a-z]?(?=\))",
        _semi_repl,
        tex,
    )

    return tex


def apply_macros(tex: str) -> str:
    """Replace literal number strings with macros.

    Skip inside \\cite{}, \\includegraphics{}, \\label{}, \\ref{}, and LaTeX comments.
    """
    # Split into protected/unprotected regions and only apply to unprotected.
    # A simple approach: process line-by-line, skipping replacement inside braces
    # of known commands.
    protected_cmd = re.compile(
        r"\\(?:cite[ptal]*|includegraphics|label|ref|input|includegraphics)"
        r"(?:\[[^\]]*\])?\{[^}]*\}"
    )

    def _replace_outside_protected(s: str, old: str, new: str) -> str:
        # Find protected spans, replace only between them
        spans = [(m.start(), m.end()) for m in protected_cmd.finditer(s)]
        if not spans:
            return s.replace(old, new)
        parts: list[str] = []
        cursor = 0
        for start, end in spans:
            parts.append(s[cursor:start].replace(old, new))
            parts.append(s[start:end])
            cursor = end
        parts.append(s[cursor:].replace(old, new))
        return "".join(parts)

    out = tex
    for literal, macro in MACRO_MAP:
        out = _replace_outside_protected(out, literal, macro + " ")
        out = out.replace(macro + "  ", macro + " ")
    return out


def insert_section_labels(tex: str, main_label: str | None) -> str:
    """Add \\label after top-level \\section{...}."""
    if main_label:
        tex = re.sub(
            r"(\\section\{[^}]+\})",
            rf"\1\n\\label{{{main_label}}}",
            tex,
            count=1,
        )

    # Subsection labels from SUBSECTION_LABELS map
    def _sub_repl(m: re.Match[str]) -> str:
        title = m.group(1).strip()
        # Normalize pandoc-isms (-- for --, spacing)
        for md_title, label in SUBSECTION_LABELS.items():
            if md_title in title or md_title.replace("--", "-") in title:
                return f"{m.group(0)}\n\\label{{{label}}}"
        return m.group(0)

    tex = re.sub(
        r"\\(?:subsection|subsubsection)\{([^}]+)\}",
        _sub_repl,
        tex,
    )
    return tex


def demote_section_heading(tex: str, include_heading: bool) -> str:
    """For Abstract, remove the pandoc \\section{Abstract} wrapping and use \\begin{abstract}."""
    if not include_heading:
        # Abstract: strip \\section{Abstract} and wrap body in Copernicus abstract env
        tex = re.sub(r"\\section\{Abstract\}\s*", "", tex)
        tex = f"\\begin{{abstract}}\n{tex.strip()}\n\\end{{abstract}}\n"
    return tex


def process_section(
    md_heading: str,
    md_body: str,
    outfile: str,
    main_label: str | None,
    include_heading: bool,
    bib_map: dict[str, str],
) -> None:
    """Convert one MD section to a LaTeX section file."""
    tex = run_pandoc(md_body)
    tex = strip_pandoc_wrappers(tex)
    tex = replace_tables(tex)
    tex = wrap_figures(tex)
    tex = apply_citation_map(tex, bib_map)
    tex = resolve_text_refs(tex)
    tex = apply_macros(tex)
    tex = substitute_unicode_math(tex)
    tex = insert_section_labels(tex, main_label)
    tex = demote_section_heading(tex, include_heading)

    # Drop trailing/leading whitespace, collapse triple blank lines
    tex = re.sub(r"\n{3,}", "\n\n", tex).strip() + "\n"

    out_path = SECTIONS_OUT / outfile
    out_path.write_text(tex)
    print(f"  wrote {out_path.relative_to(REPO)} ({len(tex)} chars)")
    warn_unmatched_citations(tex, outfile)


def main() -> None:
    if os.environ.get("CAMELS_RU_LEGACY_MD_BUILD") != "1":
        print(
            "Refusing to regenerate legacy paper/latex/ from paper/manuscript.md. "
            "Canonical manuscript source is paper/overleaf/. Set "
            "CAMELS_RU_LEGACY_MD_BUILD=1 only if you intentionally revive the "
            "legacy Markdown workflow.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print("== CAMELS-RU paper regeneration ==")
    print(f"  source:  {MD.relative_to(REPO)}")
    print(f"  target:  {SECTIONS_OUT.relative_to(REPO)}/")
    print(f"  bib:     {BIB.relative_to(REPO)}")

    bib_map = parse_bib_authors()
    print(f"  bib keys parsed: {len(bib_map)}")

    sections = split_manuscript()
    print(f"  md sections found: {len(sections)}")

    for heading, outfile, label, include in SECTION_MAP:
        if heading not in sections:
            print(f"  [SKIP] {heading} not found in MD")
            continue
        print(f"\n→ {heading}")
        process_section(heading, sections[heading], outfile, label, include, bib_map)

    print("\nDone. Legacy output only. Canonical build: cd paper/overleaf && latexmk -pdf main.tex")


if __name__ == "__main__":
    main()
