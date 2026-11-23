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


def test_cancelled_run_leaves_no_trace(tmp_path):
    import copy
    import pytest
    from backend.config import get_config
    from src.pipeline import JobCancelled, run_import
    from src.storage.project_manager import ProjectManager

    cfg = copy.deepcopy(get_config())
    cfg["storage"]["projects_dir"] = str(tmp_path / "projects")
    f = tmp_path / "scopus.csv"
    f.write_text("Authors,Title,Year,Source title,Cited by,DOI,Abstract,Document Type,EID\n"
                 "Smith J.,Deep stuff,2022,Journal X,5,10.1/abc,An abstract,Article,2-s2.0-1\n", encoding="utf-8")

    def emit(event):
        if event["type"] == "dedup":
            raise JobCancelled()

    with pytest.raises(JobCancelled):
        run_import("p", str(f), "context", cfg, emit)
    pm = ProjectManager(cfg["storage"]["projects_dir"])
    assert pm.get_papers("p") == []
    assert list(pm.sessions_dir("p").iterdir()) == []


def test_validation_sample_grows_without_repeats_and_labels(tmp_path):
    import copy
    import pytest
    from backend.config import get_config
    from src.pipeline import annotate, draw_validation_sample
    from src.storage.project_manager import ProjectManager

    cfg = copy.deepcopy(get_config())
    cfg["storage"]["projects_dir"] = str(tmp_path)
    pm = ProjectManager(str(tmp_path))
    pm.init_project("p")
    pm.save_papers("p", [rec(title=f"Paper {i}", externalIds={"DOI": f"10.1/{i}"}) for i in range(30)])
    first = draw_validation_sample("p", 10, cfg, seed=1)
    second = draw_validation_sample("p", 25, cfg, seed=2)
    assert first["added"] == 10 and second["added"] == 20          # only 20 left to draw
    assert len(set(second["sample"])) == 30
    pid = second["sample"][0]
    assert annotate("p", pid, cfg, validation="relevant")["validation"] == "relevant"
    assert annotate("p", pid, cfg, validation="")["validation"] is None
    with pytest.raises(ValueError):
        annotate("p", pid, cfg, validation="maybe")


def test_openalex_pages_without_cursor(monkeypatch):
    from src.sources import openalex as oa

    calls = []

    class Resp:
        status_code = 200
        headers = {}

        def __init__(self, params):
            self.params = params

        def raise_for_status(self):
            pass

        def json(self):
            page, per = self.params["page"], self.params["per_page"]
            n = max(0, min(per, 450 - (page - 1) * per))  # 450 results in total
            return {"meta": {"count": 450},
                    "results": [{"id": f"https://openalex.org/W{page}{i}", "title": "t"} for i in range(n)]}

    client = oa.OpenAlexClient()
    monkeypatch.setattr(client._session, "get", lambda url, params, timeout: calls.append(params) or Resp(params))
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    assert len(client.search_all("x", 1000)) == 450
    assert [c["page"] for c in calls] == [1, 2, 3] and all("cursor" not in c for c in calls)
    calls.clear()
    assert len(client.search_all("x", 150)) == 150 and len(calls) == 1


WOS_BIB = r"""
@article{ WOS:000123456700001,
Author = {Smith, John and Garc{\'{i}}a, Mar{\'{\i}}a and others},
Title = {{Deep LSTM} networks for intrusion detection: a review},
Journal = {{IEEE ACCESS}},
Year = {{2021}},
Volume = {{9}},
Abstract = {{Intrusion detection {[}1] uses na\"{i}ve Bayes \& 50\% of {NSL-KDD}.}},
Type = {{Review}},
DOI = {{10.1109/ACCESS.2021.1234}},
Unique-ID = {{WOS:000123456700001}},
Times-Cited = {{12}},
}

@inproceedings{ WOS:000123456700002,
Author = {Doe, Alice},
Title = {{Random forests on KDD} 99},
Booktitle = {{2020 IEEE CONFERENCE ON SECURITY}},
Year = {{2020}},
Unique-ID = {{WOS:000123456700002}},
}
"""


def test_parse_wos_bibtex(tmp_path):
    from src.importers.bibtex_import import looks_like_bibtex, parse_bibtex
    f = tmp_path / "savedrecs.txt"   # WoS names BibTeX downloads .txt or .bib
    f.write_text(WOS_BIB, encoding="utf-8")
    assert looks_like_bibtex(f)
    fmt, n, records = parse_bibtex(f)
    assert fmt == "wos" and n == 2
    a, b = records
    assert a["title"] == "Deep LSTM networks for intrusion detection: a review"
    assert [x["name"] for x in a["authors"]] == ["Smith, John", "García, María"]
    assert a["abstract"] == "Intrusion detection [1] uses naïve Bayes & 50% of NSL-KDD."
    assert a["externalIds"] == {"DOI": "10.1109/access.2021.1234"}
    assert a["year"] == 2021 and a["citationCount"] == 12 and a["is_review"]
    assert a["venue"] == "IEEE Access" and a["_source"] == "wos_bib"   # WoS capitals undone
    assert b["venue"] == "2020 IEEE Conference on Security"
    assert b["publicationType"] == "conference" and b["citationCount"] is None


def test_parse_generic_bibtex_macros_and_quotes(tmp_path):
    from src.importers.bibtex_import import parse_bibtex
    f = tmp_path / "zotero.bib"
    f.write_text(r'''@string{tnn = "IEEE Trans. Neural Netw."}
@comment{ignored}
@article{key1, title = "A {\v{S}}koda study", journal = tnn # " Learn.",
  year = 2019, author = "Novak, Jan and Kov{\'a}{\v r}, Petr",
  note = {Cited by: 7}, url = {https://example.org/\url}}
''', encoding="utf-8")
    fmt, n, records = parse_bibtex(f)
    assert fmt == "bibtex" and n == 1
    r = records[0]
    assert r["title"] == "A Škoda study"
    assert r["venue"] == "IEEE Trans. Neural Netw. Learn."
    assert r["year"] == 2019 and r["_source"] == "bibtex"
    assert [x["name"] for x in r["authors"]] == ["Novak, Jan", "Kovář, Petr"]


def test_apa_reference_and_in_text():
    from src.utils.apa import apa_html, apa_in_text, apa_text, reference_list_rtf
    art = rec(title="Deep LSTM Networks for Intrusion Detection: A Short-Term Study", year=2021,
              authors=[{"name": "Smith, John Michael"}, {"name": "García-López A.B."}, {"name": "Jean-Paul Sartre"}],
              venue="IEEE Access", externalIds={"DOI": "10.1/x"}, publicationType="article")
    art.update(volume="9", issue="3", pages="100-110")
    assert apa_text(art) == ("Smith, J. M., García-López, A. B., & Sartre, J.-P. (2021). Deep LSTM networks for "
                             "intrusion detection: A short-term study. IEEE Access, 9(3), 100–110. https://doi.org/10.1/x")
    assert "<i>IEEE Access</i>, <i>9</i>(3)" in apa_html(art)
    assert apa_in_text(art) == "(Smith et al., 2021)"
    conf = rec(title="Random Forests on KDD 99", year=None, authors=[{"name": "Doe, Alice"}, {"name": "Roe, Bob"}],
               venue="Proc. ICCCS", publicationType="conference", externalIds={})
    assert apa_text(conf) == "Doe, A., & Roe, B. (n.d.). Random forests on KDD 99. In Proc. ICCCS."
    assert apa_in_text(conf) == "(Doe & Roe, n.d.)"
    rtf = reference_list_rtf([conf, art])
    assert rtf.startswith(r"{\rtf1") and rtf.index("Doe") < rtf.index("Smith")   # alphabetical
    assert r"Garc\u237?a" in rtf and r"{\i IEEE Access}" in rtf
