"""The models must match the schema diagram (docs/src/build_schema.py): every table, column and nullability."""

import ast
import pathlib

import pytest
from django.apps import apps

SCHEMA_SOURCE = pathlib.Path(__file__).resolve().parents[2] / "docs" / "src" / "build_schema.py"

# Intentional differences, each with its reason.
NULLABILITY_EXCEPTIONS = {
    # Django never stores NULL here; LDAP and service accounts get an "unusable password" marker instead.
    ("users", "password_hash"),
}


def schema_tables() -> dict:
    tree = ast.parse(SCHEMA_SOURCE.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TABLES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("TABLES not found in build_schema.py")


TABLES = schema_tables()
MODELS = {model._meta.db_table: model for model in apps.get_models()}


def test_the_schema_has_42_tables_and_each_has_a_model():
    assert len(TABLES) == 42
    assert sorted(set(TABLES) - set(MODELS)) == []


@pytest.mark.parametrize("table", sorted(TABLES))
def test_columns_and_nullability_match(table):
    _, columns = TABLES[table]
    fields = {field.column: field for field in MODELS[table]._meta.concrete_fields}
    for name, _type, flags in columns:
        assert name in fields, f"{table}.{name} is in the diagram but not in the model"
        if "PK" in flags or (table, name) in NULLABILITY_EXCEPTIONS:
            continue
        nullable = "N" in flags.split()
        assert fields[name].null is nullable, f"{table}.{name}: diagram nullable={nullable}, model null={fields[name].null}"
