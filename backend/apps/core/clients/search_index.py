"""OpenSearch: one BM25 index per generation; _id = chunk ID; access_groups always in the bool filter."""

from functools import lru_cache

from django.conf import settings
from opensearchpy import OpenSearch, helpers

from . import http

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
        "analysis": {
            # File names and headings: "Balamurugan_Thangadurai_CV" -> balamurugan, thangadurai, cv
            "char_filter": {"words_apart": {"type": "mapping", "mappings": ["_ => \\u0020", ". => \\u0020"]}},
            "analyzer": {
                "title_text": {"type": "custom", "tokenizer": "standard", "char_filter": ["words_apart"], "filter": ["lowercase"]}
            },
        },
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "document_version_id": {"type": "keyword"},
            "index_generation_id": {"type": "keyword"},
            "content_hash": {"type": "keyword"},
            "access_groups": {"type": "keyword"},
            "text_content": {"type": "text"},
            "filename": {
                "type": "text",
                "analyzer": "title_text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "section_path": {
                "type": "text",
                "analyzer": "title_text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 1024}},
            },
            "page_start": {"type": "integer"},
            "page_end": {"type": "integer"},
        },
    },
}


def _verify() -> str | bool:
    return settings.OPENSEARCH_CA_CERT or False


def ping() -> bool:
    auth = (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD) if settings.OPENSEARCH_USER else None
    response = http.get(f"{settings.OPENSEARCH_URL}/_cluster/health", auth=auth, verify=_verify())
    return response.status_code == 200 and response.json().get("status") in ("green", "yellow")


@lru_cache(maxsize=1)
def client() -> OpenSearch:
    return OpenSearch(
        hosts=[settings.OPENSEARCH_URL],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        use_ssl=settings.OPENSEARCH_URL.startswith("https"),
        verify_certs=bool(settings.OPENSEARCH_CA_CERT),
        ca_certs=settings.OPENSEARCH_CA_CERT or None,
        ssl_show_warn=False,
        timeout=60,
    )


def ensure_index(name: str) -> None:
    if not client().indices.exists(index=name):
        client().indices.create(index=name, body=MAPPING)


def bulk_upsert(name: str, documents: list[dict]) -> None:
    """documents: dicts with an "_id" and the mapped fields."""
    actions = [{"_op_type": "index", "_index": name, "_id": doc.pop("_id"), "_source": doc} for doc in documents]
    helpers.bulk(client(), actions, refresh="wait_for", chunk_size=500)


def delete_where(name: str, field: str, value: str) -> None:
    client().delete_by_query(index=name, body={"query": {"term": {field: value}}}, refresh=True, conflicts="proceed")


def delete_ids(name: str, ids: list[str]) -> None:
    if ids:
        helpers.bulk(
            client(), [{"_op_type": "delete", "_index": name, "_id": i} for i in ids], refresh="wait_for", raise_on_error=False
        )


def set_access_groups(name: str, document_id: str, groups: list[str]) -> None:
    client().update_by_query(
        index=name,
        body={
            "query": {"term": {"document_id": document_id}},
            "script": {"source": "ctx._source.access_groups = params.groups", "lang": "painless", "params": {"groups": groups}},
        },
        refresh=True,
        conflicts="proceed",
    )


def count(name: str) -> int:
    client().indices.refresh(index=name)
    return int(client().count(index=name)["count"])


def all_ids(name: str) -> set[str]:
    return {
        hit["_id"]
        # clear_scroll=False: the scroll simply expires; clearing it needs a cluster permission rag_app lacks.
        for hit in helpers.scan(
            client(), index=name, query={"query": {"match_all": {}}}, _source=False, scroll="1m", clear_scroll=False
        )
    }


def search(
    name: str,
    text: str,
    *,
    generation_id: str,
    access_groups: list[str],
    size: int,
    fields: list[str] | None = None,
    fuzziness: str = "0",
) -> list[dict]:
    """BM25 search; the generation and the user's access groups are filter clauses (never 'should')."""
    if not access_groups or not text.strip():
        return []
    fields = fields or ["text_content"]
    if fields == ["text_content"] and fuzziness == "0":
        match = {"match": {"text_content": {"query": text}}}  # the original query, kept exactly for older versions
    else:
        match = {
            "multi_match": {"query": text, "fields": fields, "type": "most_fields", "fuzziness": fuzziness, "prefix_length": 1}
        }
    body = {
        "size": size,
        "query": {
            "bool": {
                "must": match,
                "filter": [{"term": {"index_generation_id": generation_id}}, {"terms": {"access_groups": access_groups}}],
            }
        },
        "_source": ["chunk_id", "document_id", "page_start", "page_end", "section_path", "filename"],
    }
    return client().search(index=name, body=body)["hits"]["hits"]


def drop(name: str) -> None:
    if client().indices.exists(index=name):
        client().indices.delete(index=name)
