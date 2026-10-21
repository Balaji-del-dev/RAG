"""Generate the PostgreSQL ER diagram (03-database-schema) from one table spec.

    python3 docs/src/build_schema.py          # writes 03-database-schema.html next to this file
    python3 docs/src/build_schema.py --sizes  # print each table's rendered size (for planning LAYOUT)
    python3 docs/src/render.py 03             # screenshots the .html to docs/images/03-database-schema.png

Tables follow section 4 of the v2 architecture brief. Columns flagged ADD and tables tagged
ADDED are recommendations beyond that brief. Graphviz (neato, pinned positions) only draws
the tables; FK lines are routed in the browser by _schema-template.html.
Uses Graphviz `dot`/`neato` when installed, otherwise the WebAssembly build
(npm i @hpcc-js/wasm-graphviz; set GRAPHVIZ_WASM to its dist/index.js if it is not resolvable).
"""
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent

# key: (label, colour, region fill, region border)
DOMAINS = {
    "A": ("4.1 · Pipeline configuration", "#7c3aed", "#fbf9ff", "#ddd0fb"),
    "B": ("4.2 · Documents & MinIO", "#c2410c", "#fffaf6", "#f3d3bd"),
    "C": ("4.3 · Processing, extraction & chunks", "#15803d", "#f8fdf9", "#c6e6d0"),
    "D": ("4.4 · Index lifecycle", "#0e7490", "#f6fcfd", "#b9dfe7"),
    "E": ("4.5 · Retrieval, answers & feedback", "#1d4ed8", "#f8faff", "#c9d7f7"),
    "F": ("4.6 · Evaluation & audit", "#be185d", "#fff8fb", "#f2c6d8"),
    "G": ("4.7 · Identity & access — authentication and authorization", "#a16207", "#fffcf2", "#ecd9a0"),
}

# (column, type, flags) — flags: PK, FK, UQ, IX, N (nullable), ADD (recommended addition)
# FK targets live in EDGES so the column lists stay readable.
TABLES = {
    # ---------------------------------------------------------------- 4.1
    "pipeline_definitions": ("A", [
        ("id", "uuid", "PK"),
        ("name", "varchar(200)", "UQ"),
        ("description", "text", "N"),
        ("is_active", "boolean", ""),
        ("created_at", "timestamptz", ""),
    ]),
    "pipeline_versions": ("A", [
        ("id", "uuid", "PK"),
        ("pipeline_id", "uuid", "FK"),
        ("version_number", "integer", "UQ"),
        ("status", "enum", ""),
        ("config_json", "jsonb", ""),
        ("retrieval_definition_id", "uuid", "FK ADD"),
        ("generation_definition_id", "uuid", "FK ADD"),
        ("created_by", "uuid → users", "N ADD"),
        ("published_at", "timestamptz", "N"),
        ("published_by", "uuid → users", "N ADD"),
    ]),
    "component_definitions": ("A", [
        ("id", "uuid", "PK"),
        ("name", "varchar(100)", "UQ"),
        ("component_type", "enum", ""),
        ("implementation_key", "varchar(200)", ""),
        ("config_schema", "jsonb", ""),
        ("is_active", "boolean", ""),
    ]),
    "pipeline_steps": ("A", [
        ("id", "uuid", "PK"),
        ("pipeline_version_id", "uuid", "FK"),
        ("component_id", "uuid", "FK"),
        ("step_order", "smallint", "UQ"),
        ("config_json", "jsonb", ""),
        ("is_enabled", "boolean", ""),
    ]),
    "model_definitions": ("A", [
        ("id", "uuid", "PK"),
        ("name", "varchar(100)", "UQ"),
        ("provider", "varchar(60)", ""),
        ("model_name", "varchar(200)", ""),
        ("model_type", "enum", ""),
        ("parameters_json", "jsonb", ""),
        ("is_active", "boolean", ""),
    ]),
    "retrieval_definitions": ("A", [
        ("id", "uuid", "PK"),
        ("name", "varchar(100)", "UQ"),
        ("dense_config", "jsonb", ""),
        ("bm25_config", "jsonb", ""),
        ("fusion_config", "jsonb", ""),
        ("reranker_config", "jsonb", ""),
        ("context_config", "jsonb", ""),
    ]),
    "generation_definitions": ("A", [
        ("id", "uuid", "PK"),
        ("name", "varchar(100)", "UQ"),
        ("model_id", "uuid", "FK"),
        ("prompt_template", "text", ""),
        ("generation_config", "jsonb", ""),
        ("citation_config", "jsonb", ""),
        ("abstention_config", "jsonb", ""),
    ]),
    # ---------------------------------------------------------------- 4.2
    "documents": ("B", [
        ("id", "uuid", "PK"),
        ("filename", "text", ""),
        ("file_extension", "varchar(20)", ""),
        ("mime_type", "varchar(120)", ""),
        ("current_version_id", "uuid → versions", "N"),
        ("lifecycle_status", "enum", "IX"),
        ("created_by", "uuid", "FK ADD"),
        ("created_at", "timestamptz", ""),
        ("updated_at", "timestamptz", ""),
        ("deleted_at", "timestamptz", "N"),
    ]),
    "document_versions": ("B", [
        ("id", "uuid", "PK"),
        ("document_id", "uuid", "FK UQ"),
        ("version_number", "integer", "UQ"),
        ("parent_version_id", "uuid → self", "N"),
        ("content_sha256", "char(64)", "IX"),
        ("file_size", "bigint", ""),
        ("storage_bucket", "varchar(63)", ""),
        ("storage_object_key", "text", ""),
        ("storage_version_id", "varchar(100)", "N"),
        ("status", "enum", ""),
    ]),
    "storage_objects": ("B", [
        ("id", "uuid", "PK"),
        ("bucket", "varchar(63)", "UQ"),
        ("object_key", "text", "UQ"),
        ("object_version_id", "varchar(100)", "N"),
        ("content_sha256", "char(64)", "IX"),
        ("size_bytes", "bigint", ""),
        ("object_type", "enum", ""),
        ("created_at", "timestamptz", ""),
    ]),
    "document_metadata": ("B", [
        ("id", "uuid", "PK"),
        ("document_version_id", "uuid", "FK UQ"),
        ("metadata_json", "jsonb", ""),
    ]),
    "extracted_artifacts": ("B", [
        ("id", "uuid", "PK"),
        ("document_version_id", "uuid", "FK"),
        ("artifact_type", "enum", ""),
        ("storage_bucket", "varchar(63)", ""),
        ("storage_object_key", "text", ""),
        ("content_sha256", "char(64)", ""),
        ("metadata_json", "jsonb", ""),
    ]),
    # ---------------------------------------------------------------- 4.3
    "processing_jobs": ("C", [
        ("id", "uuid", "PK"),
        ("document_version_id", "uuid", "FK IX"),
        ("pipeline_version_id", "uuid", "FK"),
        ("job_type", "enum", ""),
        ("status", "enum", "IX"),
        ("attempt_count", "smallint", ""),
        ("created_at", "timestamptz", "IX ADD"),
        ("started_at", "timestamptz", "N"),
        ("completed_at", "timestamptz", "N"),
        ("error_message", "text", "N"),
    ]),
    "processing_step_runs": ("C", [
        ("id", "uuid", "PK"),
        ("processing_job_id", "uuid", "FK"),
        ("step_name", "varchar(80)", ""),
        ("status", "enum", ""),
        ("input_summary", "jsonb", ""),
        ("output_summary", "jsonb", "N"),
        ("duration_ms", "integer", "N"),
        ("error_message", "text", "N"),
    ]),
    "document_elements": ("C", [
        ("id", "uuid", "PK"),
        ("document_version_id", "uuid", "FK IX"),
        ("element_type", "enum", ""),
        ("element_order", "integer", "IX"),
        ("page_number", "integer", "N"),
        ("section_path", "text", "N"),
        ("text_content", "text", ""),
        ("metadata_json", "jsonb", ""),
    ]),
    "chunks": ("C", [
        ("id", "uuid", "PK"),
        ("document_version_id", "uuid", "FK IX"),
        ("pipeline_version_id", "uuid", "FK IX ADD"),
        ("parent_chunk_id", "uuid → self", "N IX"),
        ("chunk_index", "integer", "IX"),
        ("text_content", "text", ""),
        ("token_count", "integer", ""),
        ("page_start", "integer", "N"),
        ("page_end", "integer", "N"),
        ("section_path", "text", "N"),
        ("content_hash", "char(64)", ""),
        ("metadata_json", "jsonb", ""),
    ]),
    "chunk_relationships": ("C", [
        ("id", "uuid", "PK"),
        ("source_chunk_id", "uuid", "FK"),
        ("target_chunk_id", "uuid", "FK"),
        ("relationship_type", "enum", ""),
    ]),
    "embedding_records": ("C", [
        ("id", "uuid", "PK"),
        ("chunk_id", "uuid", "FK IX"),
        ("model_id", "uuid", "FK IX"),
        ("model_version", "varchar(80)", "IX"),
        ("vector_dimension", "integer", ""),
        ("vector_point_id", "uuid", ""),
        ("content_hash", "char(64)", ""),
        ("status", "enum", ""),
    ]),
    # ---------------------------------------------------------------- 4.4
    "index_generations": ("D", [
        ("id", "uuid", "PK"),
        ("pipeline_version_id", "uuid", "FK UQ"),
        ("generation_number", "integer", "UQ"),
        ("qdrant_collection", "varchar(255)", ""),
        ("opensearch_index", "varchar(255)", ""),
        ("status", "enum", ""),
        ("published_at", "timestamptz", "N"),
    ]),
    "index_build_jobs": ("D", [
        ("id", "uuid", "PK"),
        ("index_generation_id", "uuid", "FK"),
        ("status", "enum", ""),
        ("attempt_count", "smallint", ""),
        ("started_at", "timestamptz", "N"),
        ("completed_at", "timestamptz", "N"),
        ("error_message", "text", "N"),
    ]),
    "index_memberships": ("D", [
        ("id", "uuid", "PK"),
        ("index_generation_id", "uuid", "FK UQ"),
        ("document_version_id", "uuid", "FK IX"),
        ("chunk_id", "uuid", "FK UQ"),
        ("qdrant_point_id", "uuid", ""),
        ("opensearch_document_id", "varchar(100)", ""),
        ("status", "enum", ""),
    ]),
    "index_validations": ("D", [
        ("id", "uuid", "PK"),
        ("index_generation_id", "uuid", "FK"),
        ("validation_type", "enum", ""),
        ("status", "enum", ""),
        ("expected_count", "integer", "N"),
        ("actual_count", "integer", "N"),
        ("details_json", "jsonb", ""),
    ]),
    "outbox_events": ("D", [
        ("id", "bigint", "PK"),
        ("event_type", "varchar(60)", ""),
        ("aggregate_type", "varchar(60)", ""),
        ("aggregate_id", "uuid", ""),
        ("payload", "jsonb", ""),
        ("status", "enum", "IX"),
        ("attempts", "smallint", ""),
        ("available_at", "timestamptz", "IX"),
        ("dispatched_at", "timestamptz", "N"),
        ("created_at", "timestamptz", ""),
    ]),
    # ---------------------------------------------------------------- 4.5
    "retrieval_runs": ("E", [
        ("id", "uuid", "PK"),
        ("request_id", "uuid", "UQ"),
        ("user_id", "uuid", "FK IX ADD"),
        ("query_text", "text", ""),
        ("normalized_query", "text", ""),
        ("pipeline_version_id", "uuid", "FK"),
        ("index_generation_id", "uuid", "FK IX"),
        ("status", "enum", ""),
        ("latency_ms", "integer", ""),
        ("trace_id", "varchar(64)", "IX"),
        ("created_at", "timestamptz", "IX ADD"),
    ]),
    "retrieval_results": ("E", [
        ("id", "uuid", "PK"),
        ("retrieval_run_id", "uuid", "FK IX"),
        ("chunk_id", "uuid", "FK"),
        ("retrieval_source", "enum", ""),
        ("original_rank", "smallint", ""),
        ("original_score", "real", ""),
        ("fusion_rank", "smallint", "N IX"),
        ("reranker_score", "real", "N"),
    ]),
    "answer_records": ("E", [
        ("id", "uuid", "PK"),
        ("retrieval_run_id", "uuid", "FK"),
        ("model_id", "uuid", "FK"),
        ("prompt_version", "varchar(40)", ""),
        ("answer_text", "text", "N"),
        ("citation_data", "jsonb", ""),
        ("status", "enum", ""),
        ("latency_ms", "integer", ""),
        ("token_usage_json", "jsonb", ""),
    ]),
    "user_feedback": ("E", [
        ("id", "uuid", "PK"),
        ("answer_id", "uuid", "FK"),
        ("user_id", "uuid", "FK ADD"),
        ("rating", "smallint", ""),
        ("feedback_text", "text", "N"),
        ("created_at", "timestamptz", ""),
    ]),
    "failure_cases": ("E", [
        ("id", "uuid", "PK"),
        ("retrieval_run_id", "uuid", "FK"),
        ("failure_type", "enum", ""),
        ("root_cause", "text", "N"),
        ("review_status", "enum", ""),
        ("resolution_notes", "text", "N"),
    ]),
    # ---------------------------------------------------------------- 4.6
    "evaluation_datasets": ("F", [
        ("id", "uuid", "PK"),
        ("name", "varchar(100)", "UQ"),
        ("version", "integer", "UQ"),
        ("description", "text", "N"),
    ]),
    "evaluation_cases": ("F", [
        ("id", "uuid", "PK"),
        ("dataset_id", "uuid", "FK"),
        ("question", "text", ""),
        ("expected_answer", "text", "N"),
        ("expected_sources", "jsonb", ""),
        ("case_type", "enum", ""),
        ("metadata_json", "jsonb", ""),
    ]),
    "evaluation_runs": ("F", [
        ("id", "uuid", "PK"),
        ("dataset_id", "uuid", "FK"),
        ("pipeline_version_id", "uuid", "FK"),
        ("index_generation_id", "uuid", "FK"),
        ("status", "enum", ""),
        ("summary_json", "jsonb", ""),
        ("started_at", "timestamptz", ""),
        ("completed_at", "timestamptz", "N"),
        ("approved_by", "uuid → users", "N ADD"),
    ]),
    "evaluation_results": ("F", [
        ("id", "uuid", "PK"),
        ("evaluation_run_id", "uuid", "FK IX"),
        ("evaluation_case_id", "uuid", "FK IX"),
        ("metric_name", "varchar(80)", "IX"),
        ("score", "real", ""),
        ("passed", "boolean", ""),
        ("details_json", "jsonb", ""),
    ]),
    "audit_events": ("F", [
        ("id", "bigint", "PK"),
        ("event_type", "varchar(80)", ""),
        ("entity_type", "varchar(60)", ""),
        ("entity_id", "uuid", "N"),
        ("actor", "varchar(150)", ""),
        ("actor_user_id", "uuid → users", "N ADD"),
        ("ip_address", "inet", "N ADD"),
        ("details_json", "jsonb", ""),
        ("created_at", "timestamptz", "IX"),
    ]),
    # ---------------------------------------------------------------- 4.7 identity & access
    "users": ("G", [
        ("id", "uuid", "PK"),
        ("username", "varchar(150)", "UQ"),
        ("email", "varchar(254)", "UQ"),
        ("display_name", "varchar(150)", ""),
        ("password_hash", "varchar(128)", "N"),
        ("auth_source", "enum", ""),
        ("is_active", "boolean", ""),
        ("mfa_enabled", "boolean", ""),
        ("failed_login_count", "smallint", ""),
        ("locked_until", "timestamptz", "N"),
        ("last_login", "timestamptz", "N"),
        ("created_at", "timestamptz", ""),
    ]),
    "roles": ("G", [
        ("id", "uuid", "PK"),
        ("name", "varchar(60)", "UQ"),
        ("description", "text", "N"),
        ("is_system", "boolean", ""),
    ]),
    "permissions": ("G", [
        ("id", "uuid", "PK"),
        ("codename", "varchar(100)", "UQ"),
        ("description", "text", "N"),
    ]),
    "role_permissions": ("G", [
        ("id", "uuid", "PK"),
        ("role_id", "uuid", "FK UQ"),
        ("permission_id", "uuid", "FK UQ"),
    ]),
    "user_roles": ("G", [
        ("id", "uuid", "PK"),
        ("user_id", "uuid", "FK UQ"),
        ("role_id", "uuid", "FK UQ"),
        ("granted_by", "uuid → users", "N"),
        ("granted_at", "timestamptz", ""),
    ]),
    "access_groups": ("G", [
        ("id", "uuid", "PK"),
        ("name", "varchar(100)", "UQ"),
        ("description", "text", "N"),
        ("created_at", "timestamptz", ""),
    ]),
    "user_access_groups": ("G", [
        ("id", "uuid", "PK"),
        ("user_id", "uuid", "FK UQ"),
        ("access_group_id", "uuid", "FK UQ"),
        ("granted_at", "timestamptz", ""),
    ]),
    "document_access_grants": ("G", [
        ("id", "uuid", "PK"),
        ("document_id", "uuid", "FK UQ"),
        ("access_group_id", "uuid", "FK UQ"),
        ("access_level", "enum", ""),
        ("granted_by", "uuid → users", "N"),
        ("granted_at", "timestamptz", ""),
    ]),
    "user_sessions": ("G", [
        ("id", "uuid", "PK"),
        ("user_id", "uuid", "FK IX"),
        ("session_key_hash", "char(64)", "UQ"),
        ("ip_address", "inet", "N"),
        ("user_agent", "text", "N"),
        ("created_at", "timestamptz", ""),
        ("last_seen_at", "timestamptz", ""),
        ("expires_at", "timestamptz", "IX"),
        ("revoked_at", "timestamptz", "N"),
    ]),
}

# Header tags: tables the brief marks optional, and tables this design adds.
TABLE_TAGS = {"storage_objects": "OPTIONAL", "outbox_events": "ADDED"}
TABLE_TAGS.update({n: "ADDED" for n, (d, _) in TABLES.items() if d == "G"})

# (child, fk column, parent, kind)  kind: "1" = mandatory, "0" = nullable
EDGES = [
    ("pipeline_versions", "pipeline_id", "pipeline_definitions", "1"),
    ("pipeline_versions", "retrieval_definition_id", "retrieval_definitions", "1"),
    ("pipeline_versions", "generation_definition_id", "generation_definitions", "1"),
    ("pipeline_steps", "pipeline_version_id", "pipeline_versions", "1"),
    ("pipeline_steps", "component_id", "component_definitions", "1"),
    ("generation_definitions", "model_id", "model_definitions", "1"),
    ("document_versions", "document_id", "documents", "1"),
    ("document_metadata", "document_version_id", "document_versions", "1"),
    ("extracted_artifacts", "document_version_id", "document_versions", "1"),
    ("processing_jobs", "document_version_id", "document_versions", "1"),
    ("processing_jobs", "pipeline_version_id", "pipeline_versions", "1"),
    ("processing_step_runs", "processing_job_id", "processing_jobs", "1"),
    ("document_elements", "document_version_id", "document_versions", "1"),
    ("chunks", "document_version_id", "document_versions", "1"),
    ("chunks", "pipeline_version_id", "pipeline_versions", "1"),
    ("chunk_relationships", "source_chunk_id", "chunks", "1"),
    ("chunk_relationships", "target_chunk_id", "chunks", "1"),
    ("embedding_records", "chunk_id", "chunks", "1"),
    ("embedding_records", "model_id", "model_definitions", "1"),
    ("index_generations", "pipeline_version_id", "pipeline_versions", "1"),
    ("index_build_jobs", "index_generation_id", "index_generations", "1"),
    ("index_memberships", "index_generation_id", "index_generations", "1"),
    ("index_memberships", "document_version_id", "document_versions", "1"),
    ("index_memberships", "chunk_id", "chunks", "1"),
    ("index_validations", "index_generation_id", "index_generations", "1"),
    ("retrieval_runs", "pipeline_version_id", "pipeline_versions", "1"),
    ("retrieval_runs", "index_generation_id", "index_generations", "1"),
    ("retrieval_results", "retrieval_run_id", "retrieval_runs", "1"),
    ("retrieval_results", "chunk_id", "chunks", "1"),
    ("answer_records", "retrieval_run_id", "retrieval_runs", "1"),
    ("answer_records", "model_id", "model_definitions", "1"),
    ("user_feedback", "answer_id", "answer_records", "1"),
    ("failure_cases", "retrieval_run_id", "retrieval_runs", "1"),
    ("evaluation_cases", "dataset_id", "evaluation_datasets", "1"),
    ("evaluation_runs", "dataset_id", "evaluation_datasets", "1"),
    ("evaluation_runs", "pipeline_version_id", "pipeline_versions", "1"),
    ("evaluation_runs", "index_generation_id", "index_generations", "1"),
    ("evaluation_results", "evaluation_run_id", "evaluation_runs", "1"),
    ("evaluation_results", "evaluation_case_id", "evaluation_cases", "1"),
    # 4.7 identity & access
    ("documents", "created_by", "users", "1"),
    ("retrieval_runs", "user_id", "users", "1"),
    ("user_feedback", "user_id", "users", "1"),
    ("user_roles", "user_id", "users", "1"),
    ("user_roles", "role_id", "roles", "1"),
    ("role_permissions", "role_id", "roles", "1"),
    ("role_permissions", "permission_id", "permissions", "1"),
    ("user_access_groups", "user_id", "users", "1"),
    ("user_access_groups", "access_group_id", "access_groups", "1"),
    ("document_access_grants", "document_id", "documents", "1"),
    ("document_access_grants", "access_group_id", "access_groups", "1"),
    ("user_sessions", "user_id", "users", "1"),
]

# Hand-planned grid (top-left corner of each table, in points; y grows downwards).
# Top row: 4.1 configuration · 4.4 index lifecycle · 4.6 evaluation & audit.
# Middle row: 4.2 documents · 4.3 processing & chunks · 4.5 retrieval & feedback.
# Bottom row: 4.7 identity & access, spread under all columns.
# Gaps between columns are routing gutters for the FK lines.
X = [0, 400, 790, 1220, 1640, 2080, 2480]
ROW2 = 940
ROW3 = ROW2 + 900
LAYOUT = {
    # 4.1
    "pipeline_definitions": (X[0], 0),
    "component_definitions": (X[0], 250),
    "model_definitions": (X[0], 520),
    "retrieval_definitions": (X[1], 120),
    "generation_definitions": (X[1], 450),
    "pipeline_versions": (X[2], 0),
    "pipeline_steps": (X[2], 330),
    # 4.4
    "index_generations": (X[3], 0),
    "index_memberships": (X[3], 300),
    "index_build_jobs": (X[4], 0),
    "index_validations": (X[4], 260),
    "outbox_events": (X[4], 520),
    # 4.6
    "evaluation_datasets": (X[5], 0),
    "evaluation_runs": (X[5], 220),
    "evaluation_cases": (X[6], 0),
    "evaluation_results": (X[6], 260),
    "audit_events": (X[6], 520),
    # 4.2
    "documents": (X[0], ROW2),
    "storage_objects": (X[0], ROW2 + 300),
    "document_versions": (X[1], ROW2),
    "document_metadata": (X[1], ROW2 + 330),
    "extracted_artifacts": (X[1], ROW2 + 470),
    # 4.3
    "processing_jobs": (X[2], ROW2),
    "document_elements": (X[2], ROW2 + 330),
    "processing_step_runs": (X[3], ROW2 + 330),
    "chunks": (X[3], ROW2),
    "chunk_relationships": (X[4], ROW2 + 300),
    "embedding_records": (X[4], ROW2),
    # 4.5
    "retrieval_runs": (X[5], ROW2),
    "failure_cases": (X[5], ROW2 + 330),
    "retrieval_results": (X[6], ROW2),
    "answer_records": (X[6], ROW2 + 290),
    "user_feedback": (X[5], ROW2 + 540),
    # 4.7
    "document_access_grants": (X[0], ROW3),
    "access_groups": (X[1], ROW3),
    "user_access_groups": (X[2], ROW3),
    "users": (X[3], ROW3),
    "user_roles": (X[4], ROW3),
    "user_sessions": (X[4], ROW3 + 230),
    "roles": (X[5], ROW3),
    "role_permissions": (X[6], ROW3),
    "permissions": (X[5], ROW3 + 170),
}

FONT = "Helvetica"
MONO = "Courier"


def badge(flags: str, color: str) -> str:
    fl = flags.split()
    parts = []
    for f in ("PK", "FK", "UQ", "IX"):
        if f in fl:
            fg = {"PK": "#0f172a", "FK": color, "UQ": "#475569", "IX": "#94a3b8"}[f]
            parts.append(f'<FONT COLOR="{fg}" POINT-SIZE="9.5"><B>{f}</B></FONT>')
    return " ".join(parts) or " "


def table_label(name: str, domain: str, cols) -> str:
    _, color, _, _ = DOMAINS[domain]
    tag = TABLE_TAGS.get(name)
    tag_txt = f'  <FONT POINT-SIZE="9" COLOR="#fde68a"><B>{tag}</B></FONT>' if tag else ""
    rows = [
        f'<TR><TD COLSPAN="3" BGCOLOR="{color}" ALIGN="LEFT" CELLPADDING="7">'
        f'<FONT COLOR="white" POINT-SIZE="13" FACE="{FONT}"><B>{html.escape(name)}</B></FONT>{tag_txt}</TD></TR>'
    ]
    for i, (col, typ, flags) in enumerate(cols):
        fl = flags.split()
        bg = "#fffbeb" if "ADD" in fl else ("#ffffff" if i % 2 == 0 else "#f8fafc")
        name_txt = html.escape(col)
        if "PK" in fl:
            name_txt = f"<B>{name_txt}</B>"
        if "ADD" in fl:
            name_txt = f'{name_txt} <FONT COLOR="#b45309" POINT-SIZE="10"><B>+</B></FONT>'
        typ_txt = html.escape(typ) + ("?" if "N" in fl else "")
        rows.append(
            f'<TR>'
            f'<TD PORT="{col}_w" BGCOLOR="{bg}" ALIGN="LEFT" WIDTH="40">{badge(flags, color)}</TD>'
            f'<TD BGCOLOR="{bg}" ALIGN="LEFT"><FONT FACE="{FONT}" POINT-SIZE="11" COLOR="#0f172a">{name_txt}</FONT></TD>'
            f'<TD PORT="{col}_e" BGCOLOR="{bg}" ALIGN="RIGHT"><FONT FACE="{MONO}" POINT-SIZE="10" COLOR="#64748b">{typ_txt}</FONT></TD>'
            f'</TR>'
        )
    return (
        f'<<TABLE BORDER="1.5" COLOR="{color}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" BGCOLOR="white">'
        + "".join(rows)
        + "</TABLE>>"
    )


def graph_header(engine: str) -> list:
    common = f'fontname="{FONT}", bgcolor="transparent"'
    if engine == "dot":
        return [f'  graph [rankdir=LR, nodesep=0.28, ranksep=1.15, pad=0.3, {common}];']
    return [f'  graph [layout=neato, inputscale=72, overlap=true, pad=1.2, {common}];']


def build_dot(sizes: dict | None = None) -> str:
    """Tables only. sizes=None -> plain dot graph used to measure them; otherwise pinned for neato."""
    engine = "dot" if sizes is None else "neato"
    out = ["digraph schema {", *graph_header(engine), f'  node [shape=plaintext, fontname="{FONT}", margin=0];']
    for name, (domain, cols) in TABLES.items():
        attrs = f"label={table_label(name, domain, cols)}"
        if sizes:
            x, y = LAYOUT[name]
            w, h = sizes[name]
            attrs += f', pos="{x + w / 2:.1f},{-(y + h / 2):.1f}!"'
        out.append(f"  {name} [{attrs}];")
    out.append("}")
    return "\n".join(out)


def graphviz(dot_src: str, fmt: str, engine: str) -> str:
    if shutil.which(engine):
        return subprocess.run([engine, f"-T{fmt}"], input=dot_src, capture_output=True, text=True, check=True).stdout
    script = SRC / "render-dot.mjs"
    return subprocess.run(["node", str(script), fmt, engine], input=dot_src,
                          capture_output=True, text=True, check=True).stdout


def measure() -> dict:
    data = json.loads(graphviz(build_dot(), "json", "dot"))
    return {o["name"]: (float(o["width"]) * 72, float(o["height"]) * 72) for o in data["objects"] if "width" in o}


def check_layout(sizes: dict) -> None:
    """Fail loudly if two pinned tables overlap or crowd each other vertically."""
    boxes = {n: (x, y, x + sizes[n][0], y + sizes[n][1]) for n, (x, y) in LAYOUT.items()}
    names = list(boxes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ax1, ay1, ax2, ay2 = boxes[a]
            bx1, by1, bx2, by2 = boxes[b]
            if ax1 < bx2 + 60 and bx1 < ax2 + 60 and ay1 < by2 + 40 and by1 < ay2 + 40:
                raise SystemExit(f"layout: {a} and {b} overlap or are closer than the gutter")


def main() -> None:
    sizes = measure()
    if "--sizes" in sys.argv:
        for name, (w, h) in sizes.items():
            x, y = LAYOUT.get(name, (None, None))
            print(f"{name:24s} w={w:5.0f} h={h:5.0f}  at x={x} y={y}  bottom={None if y is None else round(y + h)}")
        return
    assert set(LAYOUT) == set(TABLES), set(TABLES) ^ set(LAYOUT)
    check_layout(sizes)
    svg = graphviz(build_dot(sizes), "svg", "neato")
    svg = svg[svg.index("<svg"):]
    edges = [
        {"child": c, "col": col, "parent": p, "kind": k, "color": DOMAINS[TABLES[c][0]][1]}
        for c, col, p, k in EDGES
    ]
    columns = {name: X.index(LAYOUT[name][0]) for name in TABLES}
    stats = f"{len(TABLES)} tables · {len(EDGES)} foreign keys"
    page = (
        (SRC / "_schema-template.html").read_text()
        .replace("{{SVG}}", svg)
        .replace("{{STATS}}", stats)
        .replace("{{DOMAINS}}", json.dumps({k: list(v) for k, v in DOMAINS.items()}))
        .replace("{{TABLE_DOMAIN}}", json.dumps({n: d for n, (d, _) in TABLES.items()}))
        .replace("{{EDGES}}", json.dumps(edges))
        .replace("{{COLUMNS}}", json.dumps(columns))
    )
    (SRC / "03-database-schema.html").write_text(page)
    print(f"wrote 03-database-schema.html ({stats})")


if __name__ == "__main__":
    main()
