// Interview content for lesson 10. def: interview definition · revise: revision card ·
// qa: questions (l: B basic · I intermediate · A advanced; a: model answer; k: key words; f: likely follow-up).
window.QA = window.QA || {};
window.QA["10"] = {
  def: "<b>Data cleaning</b> is the process of removing noise from extracted text — such as repeated headers and footers, broken characters and duplicate documents — so that only meaningful content is indexed. <b>Metadata</b> is structured information attached to each document and chunk, such as title, section, page, date, language, version and access groups. Retrieval uses metadata to filter results, display citations, prefer current versions and enforce access control.",
  revise: [
    "Normalize Unicode and whitespace, repair encoding errors and rejoin hyphenated words, but store the original text for citations.",
    "Remove boilerplate such as repeated headers and footers, because it matches many queries and displaces real content.",
    "Detect exact duplicates with hashes and near-duplicates with MinHash, SimHash or embedding similarity; treat changed files as new versions.",
    "Useful metadata: title, section path, pages, dates, language, department, access groups and version identifiers.",
    "Provenance makes every chunk traceable to its document, version, page, parser and pipeline.",
  ],
  qa: [
    { l: "B", q: "Why is data cleaning important in a RAG system?",
      a: "Data cleaning is important because noise in the extracted text — repeated headers and footers, broken characters and duplicate documents — wastes tokens and is frequently retrieved instead of real content. Removing it makes each chunk more meaningful, improves retrieval precision and keeps the limited context window for useful information.",
      k: ["noise wastes tokens", "boilerplate retrieved", "retrieval precision", "duplicates"] },
    { l: "B", q: "What is metadata, and how is it used in RAG?",
      a: "Metadata is structured descriptive information about a document or chunk, such as its title, section, page number, date, department, language, version and access groups. In RAG, it is used to filter searches — for example, only current HR policies — to display citations with page numbers, to enforce access permissions and to prefer the most recent version of a document.",
      k: ["descriptive information", "filtering", "citations", "access control", "current versions"] },
    { l: "B", q: "What is deduplication, and why does it matter?",
      a: "Deduplication is the process of identifying and removing repeated content from the corpus. Without it, the same passage can occupy several of the top search results, which wastes retrieval slots and prompt tokens, and copies of different document versions can provide contradictory information to the model.",
      k: ["remove repeated content", "wasted top-k slots", "contradictory versions"] },
    { l: "I", q: "How do you detect exact and near-duplicate documents?",
      a: "Exact duplicates are detected by computing a cryptographic hash, such as SHA-256, of the file or of the normalized text and comparing the hashes. Near-duplicates — documents with the same content and only minor edits — are detected with locality-sensitive techniques such as MinHash or SimHash over word shingles, or by finding very high embedding similarity between documents or chunks.",
      k: ["SHA-256 hash", "MinHash / SimHash", "word shingles", "embedding similarity"] },
    { l: "I", q: "What metadata would you store with each chunk?",
      a: "I would store the document identifier and version, title, section path, starting and ending page, chunk index, language, document type, relevant dates such as the effective date, department or product tags, access groups, a content hash, and the versions of the parser and pipeline that produced the chunk. The fields used for filtering are also copied into the search indexes.",
      k: ["document ID and version", "section path", "pages", "dates", "access groups", "content hash", "pipeline version"] },
    { l: "I", q: "How do you handle a new version of an existing document?",
      a: "The system recognizes that the file belongs to an existing logical document but has a different content hash, and it creates a new version linked to the previous one. The new version is processed and indexed; once it is published, the previous version is marked as superseded and its chunks are removed from the search indexes, so answers never combine outdated and current rules.",
      k: ["same document, new hash", "linked versions", "supersede previous version", "remove outdated chunks"] },
    { l: "A", q: "How can metadata improve retrieval quality, beyond filtering?",
      a: "Metadata adds context that the chunk text alone may lack. Prepending the document title and section path to each chunk before embedding helps the chunk match questions that mention its topic; field boosts, such as giving titles a higher weight, improve keyword ranking; date metadata allows the system to prefer current versions; and document-type metadata allows queries to be routed to the most appropriate subset of the corpus.",
      k: ["contextual chunk headers", "title boosting", "freshness", "query routing"] },
    { l: "A", q: "What is provenance, and why does it matter?",
      a: "Provenance is the ability to trace every chunk back to the exact document, version, page, section, parser version and pipeline version that produced it. It makes citations trustworthy, allows every derived record to be deleted when a document is removed, and makes it possible to debug problems or reprocess only the content affected by a parser or pipeline change.",
      k: ["traceability", "trustworthy citations", "complete deletion", "targeted reprocessing", "debugging"] },
  ],
};
