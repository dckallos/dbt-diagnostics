# Resolve a consumed dot-path (e.g. "nodes[].relation_name") against a dbt artifact
# JSON schema, walking through node-type unions to per-definition presence records.
# Co-authored with CoCo
"""
Turns a registry path into authoritative, per-node-type presence facts for one schema
version. "[]" descends into a collection's member schema (dict values or array items).
Because `nodes`/`results` are unions of many node-type objects, a single field can be
present on some node kinds and absent on others, so resolution returns one Presence
record per concrete object reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema_model import SchemaDoc


@dataclass(frozen=True)
class Presence:
    defn: str                 # best-effort label of the object reached (title/$id)
    present: bool
    required: bool
    types: frozenset
    nullable: bool


def _split(tok: str) -> tuple[str, bool]:
    """Return (field_name, descend_into_members?) for a path token."""
    if tok.endswith("[]"):
        return tok[:-2], True
    return tok, False


def _descend(doc: SchemaDoc, frontier: list[dict], field: str, into_members: bool) -> list[dict]:
    nxt: list[dict] = []
    for obj in frontier:
        obj = doc.deref(obj)
        spec = obj.get("properties", {}).get(field) if field else obj
        if spec is None:
            continue
        if into_members:
            spec = doc.item_schema(spec)
        nxt.extend(doc.members(spec))
    return nxt


def resolve(doc: SchemaDoc, path: str) -> list[Presence]:
    """Resolve `path` against `doc`, returning a Presence per concrete object reached."""
    tokens = path.split(".")
    frontier = doc.members(doc.root_object())
    for tok in tokens[:-1]:
        field, into_members = _split(tok)
        frontier = _descend(doc, frontier, field, into_members)
        if not frontier:
            return []

    leaf, leaf_into_members = _split(tokens[-1])
    leaf_field = leaf

    out: list[Presence] = []
    for obj in frontier:
        obj = doc.deref(obj)
        props = obj.get("properties", {})
        required = set(obj.get("required", []))
        label = obj.get("title") or obj.get("$id") or obj.get("type", "?")
        if leaf_field in props:
            types, nullable = SchemaDoc.norm_type(doc.deref(props[leaf_field]) or props[leaf_field])
            out.append(Presence(str(label), True, leaf_field in required, types, nullable))
        else:
            out.append(Presence(str(label), False, False, frozenset(), False))
    return out


def present_anywhere(doc: SchemaDoc, path: str) -> bool:
    """True if the leaf field is present on at least one concrete object on the path."""
    return any(p.present for p in resolve(doc, path))
