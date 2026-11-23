"""
Parse BibTeX exports (Web of Science, Scopus, Zotero, Google Scholar…) into records.

No external dependency: a small brace-aware reader that handles the field forms
these exporters produce - {braced}, "quoted" (with braces inside), bare numbers,
@string macros and # concatenation - plus LaTeX accents and escapes.
"""
import re
import unicodedata
from pathlib import Path

from src.utils.records import classify_publication_type, detect_review, normalize_doi, unshout

# ── LaTeX → text ─────────────────────────────────────────────────────────────
_ACCENTS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
            "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
            "c": "\u0327", "k": "\u0328", "r": "\u030a"}
_SYMBOLS = {r"\ss": "ß", r"\o": "ø", r"\O": "Ø", r"\ae": "æ", r"\AE": "Æ", r"\oe": "œ",
            r"\OE": "Œ", r"\aa": "å", r"\AA": "Å", r"\l": "ł", r"\L": "Ł", r"\i": "ı",
            r"\textendash": "–", r"\textemdash": "—", r"\textquoteright": "’",
            r"\textquoteleft": "‘", r"\textregistered": "®", r"\texttrademark": "™",
            r"\textdegree": "°", r"\textbackslash": "\\"}
# Symbol accents (\'e, \'{e}, \"{o}) and letter accents (\c{c}, \v{s}, \c c). Letter accents need
# braces or a space so that commands such as \url or \vspace are not taken for accents.
_ACCENT_RE = re.compile(r"""\\([`'^"~=.])\s*(?:\{\s*(\\?[A-Za-z])\s*\}|(\\?[A-Za-z]))""")
_LETTER_ACCENT_RE = re.compile(r"\\([uvHckr])(?:\s*\{\s*(\\?[A-Za-z])\s*\}|\s+([A-Za-z])(?![A-Za-z]))")
_CMD_ARG_RE = re.compile(r"\\(?:emph|textit|textbf|textrm|textsc|textsf|texttt|mathrm|mbox|text)\s*\{([^{}]*)\}")


def _accent(m: re.Match) -> str:
    base = m.group(2) or m.group(3)
    base = {"\\i": "i", "\\j": "j"}.get(base, base)
    return unicodedata.normalize("NFC", base + _ACCENTS[m.group(1)])


def delatex(s: str) -> str:
    """Turn the LaTeX that exporters put in titles/abstracts into plain Unicode text."""
    if not s:
        return ""
    s = s.replace("{[}", "[").replace("{]}", "]")
    for _ in range(3):  # nested \emph{\textbf{…}}
        s = _CMD_ARG_RE.sub(r"\1", s)
    s = _ACCENT_RE.sub(_accent, s)
    s = _LETTER_ACCENT_RE.sub(_accent, s)
    for cmd, ch in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(re.escape(cmd) + r"(?![A-Za-z])\s*(\{\})?", lambda _m, ch=ch: ch, s)
    s = re.sub(r"\\([&%$#_{}])", r"\1", s)
    s = s.replace("---", "—").replace("--", "–").replace("~", " ")
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\\[A-Za-z]+\s*", "", s)  # any command left: drop it
    return re.sub(r"\s+", " ", s).strip()


# ── BibTeX reader ────────────────────────────────────────────────────────────
class _Reader:
    def __init__(self, text: str):
        self.t, self.i, self.n = text, 0, len(text)
        self.macros = {m: m.capitalize() for m in
                       ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")}

    def ws(self):
        while self.i < self.n and self.t[self.i].isspace():
            self.i += 1

    def braced(self) -> str:
        """At '{': return the content up to the matching '}' (braces inside kept)."""
        depth, start = 0, self.i
        while self.i < self.n:
            c = self.t[self.i]
            if c == "\\":
                self.i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return self.t[start + 1:self.i - 1]
            self.i += 1
        raise ValueError("Unbalanced braces in the BibTeX file.")

    def quoted(self) -> str:
        """At '"': return the content up to the closing '"' at brace depth 0."""
        self.i += 1
        depth, start = 0, self.i
        while self.i < self.n:
            c = self.t[self.i]
            if c == "\\":
                self.i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == '"' and depth == 0:
                self.i += 1
                return self.t[start:self.i - 1]
            self.i += 1
        raise ValueError("Unterminated quoted value in the BibTeX file.")

    def word(self) -> str:
        m = re.compile(r"[^\s,=#{}()\"]+").match(self.t, self.i)
        if not m:
            return ""
        self.i = m.end()
        return m.group(0)

    def value(self) -> str:
        parts = []
        while True:
            self.ws()
            c = self.t[self.i] if self.i < self.n else ""
            if c == "{":
                parts.append(self.braced())
            elif c == '"':
                parts.append(self.quoted())
            else:
                w = self.word()
                parts.append(self.macros.get(w.lower(), w))
            self.ws()
            if self.i < self.n and self.t[self.i] == "#":
                self.i += 1
                continue
            return "".join(parts)

    def entries(self):
        while True:
            at = self.t.find("@", self.i)
            if at < 0:
                return
            self.i = at + 1
            kind = self.word().lower()
            self.ws()
            if self.i >= self.n or self.t[self.i] not in "{(":
                continue
            close = "}" if self.t[self.i] == "{" else ")"
            self.i += 1
            if kind in ("comment", "preamble"):
                self.i -= 1
                if close == "}":
                    self.braced()
                continue
            if kind == "string":
                self.ws()
                name = self.word().lower()
                self.ws()
                if self.i < self.n and self.t[self.i] == "=":
                    self.i += 1
                    self.macros[name] = self.value()
                self.ws()
                if self.i < self.n and self.t[self.i] == close:
                    self.i += 1
                continue
            self.ws()
            key = self.word()
            fields = {}
            while True:
                self.ws()
                if self.i >= self.n:
                    break
                c = self.t[self.i]
                if c == ",":
                    self.i += 1
                    continue
                if c == close:
                    self.i += 1
                    break
                name = self.word().lower()
                self.ws()
                if not name or self.i >= self.n or self.t[self.i] != "=":
                    # malformed field: skip to the next comma or the end of the entry
                    while self.i < self.n and self.t[self.i] not in "," + close:
                        self.i += 1
                    continue
                self.i += 1
                fields[name] = self.value()
            yield kind, key, fields


# ── records ──────────────────────────────────────────────────────────────────
_ENTRY_TYPES = {"inproceedings": "conference", "conference": "conference", "proceedings": "conference",
                "incollection": "chapter", "inbook": "chapter", "book": "book", "phdthesis": "thesis",
                "mastersthesis": "thesis", "article": "article", "unpublished": "preprint"}


def detect_bib_format(entries: list[tuple[str, str, dict]]) -> str:
    sample = entries[:50]
    if any(f.get("unique-id", "").upper().startswith(("WOS:", "{WOS:"))
           or "web-of-science-index" in f or "times-cited" in f for _, _, f in sample):
        return "wos"
    if any("scopus" in (f.get("source", "") + f.get("url", "")).lower() for _, _, f in sample):
        return "scopus"
    return "bibtex"


def _authors(raw: str) -> list[dict]:
    names = []
    for part in re.split(r"\s+and\s+", raw.strip(), flags=re.IGNORECASE):
        name = delatex(part)
        if name and name.lower() != "others":
            names.append({"name": name})
    return names


def _citations(fmt: str, f: dict) -> int | None:
    raw = f.get("times-cited") or f.get("citations") or ""
    if not raw and fmt == "scopus":  # note = {Cited by: 12; All Open Access…}
        m = re.search(r"cited by:?\s*(\d+)", f.get("note", ""), re.IGNORECASE)
        raw = m.group(1) if m else ""
    m = re.search(r"\d+", raw)
    return int(m.group(0)) if m else None


def looks_like_bibtex(path: str | Path) -> bool:
    p = Path(path)
    if p.suffix.lower() == ".bib":
        return True
    try:
        head = p.read_bytes()[:4000].decode("utf-8", errors="ignore")
    except OSError:
        return False
    return re.search(r"^\s*@\w+\s*[{(]", head, re.MULTILINE) is not None


def parse_bibtex(path: str | Path) -> tuple[str, int, list[dict]]:
    """Return (format, n_entries, records). Format is 'wos', 'scopus' or 'bibtex'."""
    raw = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw = Path(path).read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ValueError("Cannot decode the file (tried UTF-8, CP1252, Latin-1).")
    entries = list(_Reader(raw).entries())
    if not entries:
        raise ValueError("No BibTeX entries found in the file.")
    fmt = detect_bib_format(entries)
    records = []
    for kind, _key, f in entries:
        title = delatex(f.get("title", ""))
        if not title:
            continue
        doc_type = delatex(f.get("type", "") or f.get("document_type", ""))
        doi = normalize_doi(delatex(f.get("doi", "")))
        year = re.search(r"\d{4}", f.get("year", "") or f.get("date", ""))
        records.append({
            "is_review": detect_review(title, doc_type),
            "title": title,
            "abstract": delatex(f.get("abstract", "")),
            "externalIds": {"DOI": doi} if doi else {},
            "year": int(year.group(0)) if year else None,
            "citationCount": _citations(fmt, f),
            "authors": _authors(f.get("author", "")),
            "venue": unshout(delatex(f.get("journal") or f.get("booktitle") or f.get("journaltitle")
                             or f.get("publisher") or "")),
            "publicationType": classify_publication_type(doc_type, _ENTRY_TYPES.get(kind, kind)),
            "openAccessPdf": None,
            "volume": delatex(f.get("volume", "")),
            "issue": delatex(f.get("number", "") or f.get("issue", "")),
            "pages": delatex(f.get("pages", "") or f.get("article-number", "")).replace("–", "-"),
            "_source": "bibtex" if fmt == "bibtex" else f"{fmt}_bib",
        })
    return fmt, len(entries), records
