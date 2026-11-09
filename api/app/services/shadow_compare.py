from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any


def _json_value(value: Any) -> Any:
    return str(value) if isinstance(value, Decimal) else value


def compare_rows(reference: list[dict], migrated: list[dict], keys: tuple[str, ...], tolerance: Decimal, sample_limit: int) -> dict:
    ref_groups, got_groups = defaultdict(list), defaultdict(list)
    for row in reference: ref_groups[tuple(row.get(key) for key in keys)].append(row)
    for row in migrated: got_groups[tuple(row.get(key) for key in keys)].append(row)
    duplicate_keys = {key for key, rows in ref_groups.items() if len(rows) != 1} | {key for key, rows in got_groups.items() if len(rows) != 1}
    missing = set(ref_groups) - set(got_groups)
    unexpected = set(got_groups) - set(ref_groups)
    samples, column_mismatches, null_mismatches, precision = [], 0, 0, 0
    matched = 0
    for key in sorted(set(ref_groups) & set(got_groups), key=str):
        if key in duplicate_keys:
            continue
        expected, actual = ref_groups[key][0], got_groups[key][0]
        row_matches = True
        for column in sorted(set(expected) | set(actual)):
            if column in keys:
                continue
            left, right = expected.get(column), actual.get(column)
            if left is None or right is None:
                equal = left is right
                if not equal: null_mismatches += 1
            else:
                try:
                    difference = abs(Decimal(str(left)) - Decimal(str(right)))
                    equal = difference <= tolerance
                    if not equal: precision += 1
                except (InvalidOperation, ValueError):
                    equal = left == right
            if not equal:
                row_matches = False
                column_mismatches += 1
                if len(samples) < sample_limit:
                    samples.append({"key": [_json_value(v) for v in key], "column": column, "expected": _json_value(left), "actual": _json_value(right)})
        if row_matches: matched += 1
    for kind, keyset in (("missing", missing), ("unexpected", unexpected)):
        for key in sorted(keyset, key=str):
            if len(samples) < sample_limit: samples.append({"key": [_json_value(v) for v in key], "kind": kind})
    passed = not (missing or unexpected or duplicate_keys or column_mismatches)
    return {
        "comparison_result": "PASS" if passed else "FAIL", "reference_row_count": len(reference), "migrated_row_count": len(migrated),
        "matched_rows": matched, "missing_rows": len(missing), "unexpected_rows": len(unexpected),
        "duplicate_key_mismatches": len(duplicate_keys), "column_mismatches": column_mismatches,
        "null_mismatches": null_mismatches, "numeric_precision_differences": precision, "mismatch_samples": samples,
    }
