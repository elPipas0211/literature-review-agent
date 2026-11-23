// Human-readable names for the `_source` / PRISMA source keys written by the backend.
export const SOURCE_LABELS = {
  openalex: 'OpenAlex',
  citation_search: 'Citation searching',
  scopus_csv: 'Scopus (CSV)',
  wos_csv: 'Web of Science (CSV / tab-delimited)',
  zotero_csv: 'Zotero (CSV)',
  scopus_bib: 'Scopus (BibTeX)',
  wos_bib: 'Web of Science (BibTeX)',
  bibtex: 'BibTeX file',
  semantic_scholar: 'Semantic Scholar (legacy)',
}

export const sourceLabel = (key) => SOURCE_LABELS[key] || key
