"""Input validation for catalog request submissions.

Validates submitted inputs against a catalog item's input_schema. Returns a
(cleaned_values, errors) tuple. Pure functions, no I/O.
"""
from __future__ import annotations

import re

DNS_NAME = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,61}[a-z0-9])?$")
CIDR = re.compile(r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$")


def validate_inputs(schema: list[dict], inputs: dict) -> tuple[dict, list[str]]:
    cleaned: dict = {}
    errors: list[str] = []
    inputs = inputs or {}

    for field in schema:
        name = field["name"]
        label = field.get("label", name)
        ftype = field.get("type", "text")
        required = field.get("required", False)
        raw = inputs.get(name, field.get("default"))

        if ftype == "checkbox":
            cleaned[name] = bool(raw)
            continue

        if raw in (None, ""):
            if required:
                errors.append(f"{label} is required.")
            else:
                if "default" in field:
                    cleaned[name] = field["default"]
            continue

        if ftype == "number":
            try:
                cleaned[name] = float(raw) if "." in str(raw) else int(raw)
            except (TypeError, ValueError):
                errors.append(f"{label} must be a number.")
            continue

        if ftype == "select":
            opts = field.get("options", [])
            if opts and str(raw) not in opts:
                errors.append(f"{label} must be one of: {', '.join(opts)}.")
            else:
                cleaned[name] = str(raw)
            continue

        # text
        value = str(raw).strip()
        if name in ("name",) and not DNS_NAME.match(value):
            errors.append(f"{label} is not a valid name (use lowercase letters, digits and hyphens).")
        elif name == "cidr" and not CIDR.match(value):
            errors.append(f"{label} must be a CIDR block, e.g. 10.0.0.0/16.")
        else:
            cleaned[name] = value

    return cleaned, errors
