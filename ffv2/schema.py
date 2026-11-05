"""Bounded typed JSON values; caller-supplied command/unknown field গ্রহণ নয়।"""
from __future__ import annotations

import math
import re

from .errors import FFV2Error


def validate(value, rule, path="spec", depth=0):
    if depth > 6:
        raise FFV2Error("invalid_spec", "Job spec nesting সীমার বাইরে।", details={"field": path})
    kind = rule["type"]
    valid = ((kind == "string" and isinstance(value, str)) or
             (kind == "integer" and type(value) is int) or
             (kind == "number" and type(value) in (int, float) and math.isfinite(value)) or
             (kind == "boolean" and type(value) is bool) or
             (kind == "array" and isinstance(value, list)) or
             (kind == "object" and isinstance(value, dict)))
    if not valid or ("enum" in rule and value not in rule["enum"]):
        raise FFV2Error("invalid_spec", "Job field-এর type/value গ্রহণযোগ্য নয়।", details={"field": path})
    for name, compare in (("minimum", lambda a, b: a >= b), ("maximum", lambda a, b: a <= b),
                          ("exclusiveMinimum", lambda a, b: a > b)):
        if name in rule and not compare(value, rule[name]):
            raise FFV2Error("invalid_spec", "Job field সীমার বাইরে।", details={"field": path})
    if kind == "string" and not rule.get("minLength", 0) <= len(value) <= rule.get("maxLength", 4096):
        raise FFV2Error("invalid_spec", "Job string-এর দৈর্ঘ্য গ্রহণযোগ্য নয়।", details={"field": path})
    if kind == "string" and "pattern" in rule and not re.fullmatch(rule["pattern"], value):
        raise FFV2Error("invalid_spec", "Job string format গ্রহণযোগ্য নয়।", details={"field": path})
    if kind == "array":
        if not rule.get("minItems", 0) <= len(value) <= rule.get("maxItems", 16):
            raise FFV2Error("invalid_spec", "Job array-এর দৈর্ঘ্য সীমার বাইরে।", details={"field": path})
        for index, item in enumerate(value):
            validate(item, rule["items"], path + "[" + str(index) + "]", depth + 1)
    if kind == "object":
        properties = rule["properties"]
        unknown = sorted(set(value) - set(properties))
        missing = sorted(set(rule.get("required", ())) - set(value))
        if unknown or missing:
            raise FFV2Error("invalid_spec", "Job spec-এর field ঠিক করুন।", details={"field": path, "unknown": unknown, "missing": missing})
        for name, item in value.items():
            validate(item, properties[name], path + "." + name, depth + 1)
    return value
