# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal JSON Schema (draft 2020-12 subset) validator, standard library only.

Blender does not bundle the `jsonschema` package, so the contract is checked
with this subset. The schema files themselves stay standard JSON Schema, so
any external tool can validate a contract too.

Unsupported keywords are rejected when a schema is loaded instead of being
ignored, so a schema can never silently check less than it appears to.
"""

import json
import re

ANNOTATIONS = {
    "$schema", "$id", "$comment", "title", "description", "default",
    "examples", "deprecated", "readOnly", "writeOnly", "$defs",
}
SUPPORTED = {
    "type", "properties", "required", "additionalProperties", "enum", "const",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minItems", "maxItems", "items", "prefixItems", "uniqueItems",
    "minLength", "maxLength", "pattern", "$ref", "allOf", "anyOf", "oneOf",
    "not", "if", "then", "else", "minProperties", "propertyNames",
}


class SchemaError(Exception):
    """The schema itself is malformed or uses an unsupported keyword."""


def _check_keywords(node, path="#"):
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        raise SchemaError(f"{path}: schema must be an object or boolean")
    for key, value in node.items():
        if key in ANNOTATIONS:
            if key == "$defs":
                for name, sub in value.items():
                    _check_keywords(sub, f"{path}/$defs/{name}")
            continue
        if key not in SUPPORTED:
            raise SchemaError(f"{path}: unsupported keyword '{key}'")
        if key in ("properties",):
            for name, sub in value.items():
                _check_keywords(sub, f"{path}/properties/{name}")
        elif key in ("additionalProperties", "items", "not", "if", "then",
                     "else", "propertyNames"):
            _check_keywords(value, f"{path}/{key}")
        elif key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            for i, sub in enumerate(value):
                _check_keywords(sub, f"{path}/{key}/{i}")


def load_schema(path):
    with open(path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    _check_keywords(schema)
    return schema


def _type_ok(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, (list, tuple))
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "null":
        return value is None
    raise SchemaError(f"unknown type '{name}'")


def _resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise SchemaError(f"only local $ref is supported, got '{ref}'")
    node = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _validate(value, schema, root, path, errors):
    if schema is True:
        return
    if schema is False:
        errors.append((path, "value is not allowed here"))
        return

    if "$ref" in schema:
        _validate(value, _resolve_ref(root, schema["$ref"]), root, path, errors)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            errors.append((path, f"expected type {'/'.join(types)}, got {type(value).__name__}"))
            return

    if "const" in schema and value != schema["const"]:
        errors.append((path, f"must equal {schema['const']!r}"))
    if "enum" in schema and value not in schema["enum"]:
        errors.append((path, f"must be one of {schema['enum']!r}, got {value!r}"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append((path, f"must be >= {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append((path, f"must be <= {schema['maximum']}"))
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append((path, f"must be > {schema['exclusiveMinimum']}"))
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append((path, f"must be < {schema['exclusiveMaximum']}"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append((path, f"length must be >= {schema['minLength']}"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append((path, f"length must be <= {schema['maxLength']}"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append((path, f"must match pattern {schema['pattern']!r}"))

    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append((path, f"must have at least {schema['minItems']} items"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append((path, f"must have at most {schema['maxItems']} items"))
        if schema.get("uniqueItems"):
            seen = []
            for item in value:
                if item in seen:
                    errors.append((path, f"items must be unique, {item!r} repeats"))
                    break
                seen.append(item)
        prefix = schema.get("prefixItems", [])
        for i, sub in enumerate(prefix):
            if i < len(value):
                _validate(value[i], sub, root, f"{path}/{i}", errors)
        if "items" in schema:
            for i in range(len(prefix), len(value)):
                _validate(value[i], schema["items"], root, f"{path}/{i}", errors)

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append((path, f"missing required key '{key}'"))
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            errors.append((path, f"must have at least {schema['minProperties']} keys"))
        props = schema.get("properties", {})
        for key, item in value.items():
            if "propertyNames" in schema:
                _validate(key, schema["propertyNames"], root, f"{path}/{key}", errors)
            if key in props:
                _validate(item, props[key], root, f"{path}/{key}", errors)
            elif "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    errors.append((path, f"unknown key '{key}'"))
                else:
                    _validate(item, extra, root, f"{path}/{key}", errors)

    for sub in schema.get("allOf", []):
        _validate(value, sub, root, path, errors)
    if "anyOf" in schema:
        if not any(not _collect(value, s, root, path) for s in schema["anyOf"]):
            errors.append((path, "does not match any allowed form (anyOf)"))
    if "oneOf" in schema:
        matches = sum(1 for s in schema["oneOf"] if not _collect(value, s, root, path))
        if matches != 1:
            errors.append((path, f"must match exactly one form (oneOf), matched {matches}"))
    if "not" in schema and not _collect(value, schema["not"], root, path):
        errors.append((path, "matches a forbidden form (not)"))
    if "if" in schema:
        branch = "then" if not _collect(value, schema["if"], root, path) else "else"
        if branch in schema:
            _validate(value, schema[branch], root, path, errors)


def _collect(value, schema, root, path):
    errs = []
    _validate(value, schema, root, path, errs)
    return errs


def validate(value, schema):
    """Return a list of (json_pointer, message) errors. Empty means valid."""
    errors = []
    _validate(value, schema, schema, "", errors)
    return errors
