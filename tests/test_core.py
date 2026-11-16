"""Fast tests for the pure-Python parts (no model download, no network)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.scoring import score_papers
from src.filters.flags import compute_flags
from src.importers.csv_import import parse_csv
from src.utils.bibtex_exporter import assign_cite_keys, export_bibtex, latex_escape, split_name
from src.utils.deduplication import dedupe_batch, match_library
from src.utils.exporters import to_csv, to_ris
from src.utils.records import classify_publication_type, finalize_record, normalize_doi


def rec(**kw):
    base = {"title": "A study", "abstract": "x", "year": 2020, "citationCount": 1, "authors": [],
            "_source": "test"}
    return finalize_record({**base, **kw})


def test_normalize_doi_variants():
    for raw in ("https://doi.org/10.1/ABC", "http://dx.doi.org/10.1/abc", "doi: 10.1/abc", " 10.1/AbC "):
        assert normalize_doi(raw) == "10.1/abc"
    assert normalize_doi("") is None


def test_dedupe_merges_doi_variants_and_titles():
    a = rec(title="Attention is all you need", externalIds={"DOI": "https://doi.org/10.1/X"},
            abstract="", _source="openalex")
    b = rec(title="Attention Is All You Need.", externalIds={"DOI": "10.1/x"}, citationCount=99,
            _source="semantic_scholar")
    c = rec(title="Something else entirely", externalIds={})
    kept, removed = dedupe_batch([a, b, c])
    assert removed == 1 and len(kept) == 2
    merged = next(p for p in kept if p["externalIds"].get("DOI") == "10.1/x")
    assert merged["abstract"] == "x" and merged["citationCount"] == 99
    assert set(merged["_sources"]) == {"openalex", "semantic_scholar"}


def test_match_library_by_title_without_doi():
    lib = [rec(title="Deep learning for anomaly detection: a survey")]
    new, matched = match_library([rec(title="Deep Learning for Anomaly Detection - A Survey"),
                                  rec(title="Totally different")], lib)
    assert len(matched) == 1 and len(new) == 1


def test_flags_never_drop_and_floor_optional():
    p = rec(abstract="", externalIds={}, year=2010, citationCount=3)
    assert set(compute_flags(p, {"enabled": False})) == {"missing_abstract", "missing_doi"}
    floors = {"enabled": True, "pre_2015": {"year_cutoff": 2015, "min_citations": 500}}
    assert "below_citation_floor" in compute_flags(p, floors)


def test_split_name_formats():
    assert split_name("Smith J.") == ("Smith", "J.")
    assert split_name("Smith, John") == ("Smith", "John")
    assert split_name("John Smith") == ("Smith", "John")
    assert split_name("Ludwig van Beethoven") == ("van Beethoven", "Ludwig")
    assert split_name("Garcia-Lopez A.B.") == ("Garcia-Lopez", "A.B.")


def test_bibtex_escaping_types_and_keys():
    p1 = rec(title="Deep LSTM & IoT: 50% gains", authors=[{"name": "Smith J."}], year=2021,
             externalIds={"DOI": "10.1/a"}, venue="Proc. A & B", publicationType="conference")
    p2 = rec(title="Deep nets", authors=[{"name": "John Smith"}], year=2021, externalIds={"DOI": "10.1/b"})
    keys = assign_cite_keys([p1, p2])
    assert keys[p1["id"]] == "smith2021deep" and keys[p2["id"]] == "smith2021deepa"
    bib = export_bibtex([p1, p2])
    assert "@inproceedings{smith2021deep," in bib
    assert r"{LSTM} \& {IoT}: 50\% gains" in bib
    assert "author    = {Smith, J.}" in bib
    assert r"booktitle = {Proc. A \& B}" in bib
    assert latex_escape("a_b#c") == r"a\_b\#c"
    p3 = rec(title="Self-Supervised COVID-19 Time-Series", externalIds={"DOI": "10.1/c"})
    assert "title     = {Self-Supervised {COVID-19} Time-Series}" in export_bibtex([p3])


def test_scoring_rescales_and_labels():
    papers = [rec(citationCount=0), rec(citationCount=300, title="other")]
    ev = {"similarity_range": [0.75, 0.90], "weights": {"semantic": 0.8, "impact": 0.2},
          "citation_ref": 300, "thresholds": {"relevant": 0.55, "potentially": 0.35}}
    score_papers(papers, np.array([0.74, 0.90]), ev)
    assert papers[0]["evaluation"]["semantic_score"] == 0 and papers[0]["evaluation"]["category"] == "no_relevante"
    assert papers[1]["evaluation"]["score"] == 1.0 and papers[1]["evaluation"]["category"] == "relevante"


def test_publication_type_mapping():
    assert classify_publication_type("conference", "article") == "conference"
    assert classify_publication_type("Conference Paper") == "conference"
    assert classify_publication_type("Book Chapter") == "chapter"
    assert classify_publication_type("JournalArticle") == "article"
    assert classify_publication_type("preprint") == "preprint"


def test_parse_scopus_csv(tmp_path):
    f = tmp_path / "scopus.csv"
    f.write_text(
        "Authors,Author full names,Title,Year,Source title,Cited by,DOI,Abstract,Document Type,EID\n"
        '"Smith J.; Doe A.","Smith, John (111); Doe, Alice (222)",Deep stuff,2022,Journal X,5,'
        '10.1/ABC,An abstract,Conference Paper,2-s2.0-1\n'
        ',,No abstract paper,2019,Journal Y,,,[No abstract available],Article,2-s2.0-2\n',
        encoding="utf-8")
    fmt, n, records = parse_csv(f)
    assert fmt == "scopus" and n == 2
    assert records[0]["authors"] == [{"name": "Smith, John"}, {"name": "Doe, Alice"}]
    assert records[0]["externalIds"] == {"DOI": "10.1/abc"}
    assert records[0]["publicationType"] == "conference"
    assert records[1]["abstract"] == "" and records[1]["citationCount"] is None


def test_parse_wos_tab_tags(tmp_path):
    f = tmp_path / "wos.txt"
    f.write_text("PT\tAU\tAF\tTI\tSO\tDT\tAB\tZ9\tPY\tDI\tUT\n"
                 "J\tSmith, J\tSmith, John\tA title\tJOURNAL Z\tArticle\tAbs\t7\t2020\t10.2/x\tWOS:1\n",
                 encoding="utf-8")
    fmt, _, records = parse_csv(f)
    assert fmt == "wos" and records[0]["citationCount"] == 7 and records[0]["authors"][0]["name"] == "Smith, John"


def test_exports_contain_all_fields():
    p = rec(title="T", authors=[{"name": "Smith, J."}], externalIds={"DOI": "10.1/z"})
    p["flags"] = ["missing_abstract"]
    csv_text = to_csv([p])
    assert csv_text.startswith("﻿id,title,abstract") and "10.1/z" in csv_text
    ris = to_ris([p])
    assert "TY  - JOUR" not in ris or "TI  - T" in ris
    assert "DO  - 10.1/z" in ris and ris.strip().endswith("ER  -")


def test_review_detection_and_merge_keeps_reading_list():
    from src.utils.records import detect_review
    assert detect_review("A Survey of Deep Anomaly Detection")
    assert detect_review("Some title", "review")
    assert not detect_review("LSTM autoencoders for sensors")
    old = rec(title="Same paper", externalIds={"DOI": "10.1/s"})
    old.update(starred=True, note="read first")
    new = rec(title="Same paper", externalIds={"DOI": "10.1/s"}, abstract="longer abstract", citationCount=50)
    merged = {**old, **__import__("src.utils.deduplication", fromlist=["x"]).merge_records(old, new)}
    assert merged["starred"] and merged["note"] == "read first"


def test_keyword_filter_and_cluster_labels():
    from src.keywords import _pick, label_from_keywords
    picked = _pick([("datasets demonstrate", 0.9), ("anomaly detection", 0.8), ("detecting anomalies", 0.7),
                    ("lstm autoencoder", 0.6), ("2020", 0.5)], 5)
    assert picked == ["anomaly detection", "lstm autoencoder"]
    shared = ["anomaly detection"]
    a = [{"keywords": shared + ["autoencoder"]}, {"keywords": shared + ["autoencoder"]}]
    b = [{"keywords": shared + ["transformer"]}, {"keywords": shared + ["transformer"]}]
    labels = label_from_keywords([a, b], n=2)
    assert labels[0][0] == "autoencoder" and labels[1][0] == "transformer"


def test_env_settings_roundtrip(tmp_path, monkeypatch):
    import os
    import backend.config as bc
    monkeypatch.setattr(bc, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)
    (tmp_path / ".env").write_text("# local secrets\nOTHER=1\n", encoding="utf-8")
    bc.save_openalex_settings(api_key="abc123")
    assert bc.get_config()["sources"]["openalex"]["api_key"] == "abc123"
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OTHER=1" in text and "OPENALEX_API_KEY=abc123" in text
    bc.save_openalex_settings(api_key="")  # remove
    assert "OPENALEX_API_KEY" not in (tmp_path / ".env").read_text(encoding="utf-8")
    assert bc.get_config()["sources"]["openalex"]["api_key"] is None
    assert "OPENALEX_API_KEY" not in os.environ
    bc._config = None


def test_openalex_rate_limit_gives_clear_error(monkeypatch):
    import pytest
    from src.sources import openalex as oa

    class Resp:
        status_code = 429
        headers = {"Retry-After": "0"}

    client = oa.OpenAlexClient()
    monkeypatch.setattr(client._session, "get", lambda *a, **k: Resp())
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    with pytest.raises(oa.OpenAlexError, match="API key"):
        client.search_all("x", 10)
    keyed = oa.OpenAlexClient(api_key="k")
    seen = {}
    monkeypatch.setattr(keyed._session, "get", lambda url, params, timeout: seen.update(params) or Resp())
    with pytest.raises(oa.OpenAlexError):
        keyed.search_all("x", 10)
    assert seen["api_key"] == "k"
