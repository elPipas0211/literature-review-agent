"""
APA 7th edition references and in-text citations.

Each reference is built as a list of (text, italic) runs, so the same citation
can be rendered as plain text, HTML (<i>) or RTF (for Word) without losing the
italics APA requires.

Limits worth knowing: titles are converted to sentence case automatically,
keeping acronyms (LSTM, IoT, NSL-KDD) and a short list of proper nouns; other
proper nouns ("Kalman", "Python") may need a manual capital. Missing volume,
issue or pages are simply left out.
"""
import html
import re

from src.utils.bibtex_exporter import split_name
from src.utils.records import get_doi, unshout

Runs = list[tuple[str, bool]]

# Proper nouns common in technical titles that sentence case must not lowercase.
_PROPER = {
    "bayes", "bayesian", "gaussian", "markov", "markovian", "kalman", "fourier", "monte", "carlo",
    "poisson", "euclidean", "boltzmann", "pareto", "shapley", "hilbert", "laplace", "laplacian",
    "newton", "turing", "hessian", "jacobian", "wiener", "dirichlet", "bernoulli", "lyapunov",
    "levenshtein", "hamming", "manhattan", "mahalanobis", "pearson", "spearman", "student",
    "english", "spanish", "chinese", "european", "american", "african", "asian", "latin",
    "colombia", "colombian", "india", "indian", "china", "brazil", "mexico", "spain", "europe",
    "internet", "android", "linux", "windows", "python", "java", "twitter", "facebook", "google",
    "amazon", "microsoft", "wikipedia", "covid", "kdd", "unsw", "cicids", "darpa", "nsl",
}


def _initials(first: str) -> str:
    """'John Michael' -> 'J. M.', 'Jean-Paul' -> 'J.-P.', 'A.B.' -> 'A. B.'."""
    first = first.replace(".", ". ").strip()
    out = []
    for token in first.split():
        parts = [p for p in token.split("-") if p]
        if parts:
            out.append("-".join(f"{p[0].upper()}." for p in parts))
    return " ".join(out)


def _author(name: str) -> str:
    last, first = split_name(name)
    if not last:
        return ""
    ini = _initials(first)
    return f"{last}, {ini}" if ini else last


def _author_list(authors: list[dict]) -> str:
    names = [n for n in (_author(a.get("name", "")) for a in authors or []) if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) <= 20:
        return ", ".join(names[:-1]) + ", & " + names[-1]
    return ", ".join(names[:19]) + ", . . . " + names[-1]   # APA 7: first 19, ellipsis, last


def sentence_case(title: str) -> str:
    """APA sentence case: first word and the first word after a colon keep their capital."""
    words = (title or "").split()
    out, capitalize_next = [], True
    for w in words:
        m = re.match(r"^(\W*)(.*?)(\W*)$", w)
        lead, core, trail = m.groups()
        parts = core.split("-")   # each part of "Short-Term" / "NSL-KDD" is judged on its own
        for k, part in enumerate(parts):
            keep = (
                (capitalize_next and k == 0)
                or not part
                or any(c.isupper() for c in part[1:])               # LSTM, IoT, KDD, McDonald
                or any(c.isdigit() for c in part)                   # COVID-19, KDD99
                or part.lower() in _PROPER
                or part == "I"
            )
            if not keep and part[:1].isupper():
                parts[k] = part[0].lower() + part[1:]
        core = "-".join(parts)
        if capitalize_next and core[:1].islower():
            core = core[0].upper() + core[1:]
        out.append(lead + core + trail)
        capitalize_next = trail.endswith((":", "?", "!")) if trail else False
    return " ".join(out)


def _end(text: str) -> str:
    """Terminate an element with a period unless it already ends in . ? or !"""
    text = text.strip()
    return text if text.endswith((".", "?", "!")) else text + "."


def _pages(p: dict) -> str:
    return (p.get("pages") or "").replace("--", "–").replace("-", "–").strip()


def apa_runs(p: dict) -> Runs:
    authors = _author_list(p.get("authors") or [])
    year = f"({p['year']})" if p.get("year") else "(n.d.)"
    title = sentence_case(p.get("title") or "Untitled")
    venue = unshout(p.get("venue"))
    kind = p.get("publicationType") or "article"
    doi = get_doi(p)
    link = f"https://doi.org/{doi}" if doi else ""
    vol, issue, pages = (p.get("volume") or "").strip(), (p.get("issue") or "").strip(), _pages(p)

    runs: Runs = []
    head = f"{_end(authors)} {year}. " if authors else ""
    if kind in ("book", "thesis"):
        bare = title.strip().rstrip(".")
        title_runs = [(bare, True)]
        if kind == "thesis":
            title_runs.append((" [Thesis]", False))
        title_runs.append((" " if bare.endswith(("?", "!")) and kind != "thesis" else ". ", False))
    else:
        title_runs = [(_end(title) + " ", False)]

    if authors:
        runs.append((head, False))
        runs += title_runs
    else:  # no author: the title moves to the author position
        runs += title_runs
        runs.append((f"{year}. ", False))

    if kind in ("conference", "chapter") and venue:
        runs.append(("In ", False))
        runs.append((venue, True))
        runs.append((f" (pp. {pages}). " if pages else ". ", False))
    elif kind in ("book", "thesis"):
        if venue:
            runs.append((_end(venue) + " ", False))
    elif venue:  # journal article, preprint, other
        runs.append((venue, True))
        if vol:
            runs.append((", ", False))
            runs.append((vol, True))
            if issue:
                runs.append((f"({issue})", False))
        if pages:
            runs.append((f", {pages}", False))
        runs.append((". ", False))
    if link:
        runs.append((link, False))
    return [(t, i) for t, i in runs if t]


def apa_text(p: dict) -> str:
    return "".join(t for t, _ in apa_runs(p)).strip()


def apa_html(p: dict) -> str:
    return "".join(f"<i>{html.escape(t)}</i>" if i else html.escape(t) for t, i in apa_runs(p)).strip()


def apa_in_text(p: dict) -> str:
    """Parenthetical citation: (Smith, 2021), (Smith & Doe, 2021), (Smith et al., 2021)."""
    lasts = [split_name(a.get("name", ""))[0] for a in p.get("authors") or []]
    lasts = [l for l in lasts if l]
    year = p.get("year") or "n.d."
    if not lasts:
        short = sentence_case(p.get("title") or "Untitled").split(":")[0]
        who = f"“{' '.join(short.split()[:6])}”"
    elif len(lasts) == 1:
        who = lasts[0]
    elif len(lasts) == 2:
        who = f"{lasts[0]} & {lasts[1]}"
    else:
        who = f"{lasts[0]} et al."
    return f"({who}, {year})"


def _sort_key(p: dict) -> tuple:
    first = split_name((p.get("authors") or [{}])[0].get("name", ""))[0] if p.get("authors") else ""
    return ((first or p.get("title") or "").lower(), p.get("year") or 0, (p.get("title") or "").lower())


def _rtf_escape(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif code < 128:
            out.append(ch)
        elif code <= 0xFFFF:
            out.append(f"\\u{code if code < 32768 else code - 65536}?")
        else:  # astral plane: write as a UTF-16 surrogate pair
            code -= 0x10000
            for unit in (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)):
                out.append(f"\\u{unit - 65536}?")
    return "".join(out)


def reference_list_rtf(papers: list[dict]) -> str:
    """A Word-ready reference list: alphabetical, hanging indent, italics kept."""
    body = []
    for p in sorted(papers, key=_sort_key):
        runs = "".join("{\\i " + _rtf_escape(t) + "}" if i else _rtf_escape(t) for t, i in apa_runs(p))
        body.append("{\\pard\\fi-720\\li720\\sa240\\sl480\\slmult1 " + runs + "\\par}")
    return ("{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Times New Roman;}}\\f0\\fs24\n"
            "{\\pard\\qc\\b References\\par}\n" + "\n".join(body) + "\n}")


def reference_list_text(papers: list[dict]) -> str:
    return "\n\n".join(apa_text(p) for p in sorted(papers, key=_sort_key)) + "\n"
