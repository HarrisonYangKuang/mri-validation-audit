"""Audit exact-report/scanner-proxy overlap using only Python's standard library.

AI-assisted standalone adaptation of the grouping idea documented in
Ou, Y. K. (2026), Could Your MRI CV Be Learning the Scanner? See NOTICE.md.
The CLI does not read DICOM files, train a model, or write record-level files.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping, Sequence
import unicodedata


@dataclass(frozen=True)
class Record:
    """One locally authorized observation; IDs and source values stay in memory."""

    record_id: str
    report: str | None
    scanner: Mapping[str, str | None]


@dataclass(frozen=True)
class Grouping:
    components: tuple[tuple[str, ...], ...]
    report_keys: Mapping[str, str | None]
    scanner_keys: Mapping[str, str | None]


def normalize_text(value: str | None) -> str:
    """Normalize Unicode, case and whitespace; do not infer semantic similarity."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Report and scanner values must be strings or null")
    text = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", text).strip()


def report_fingerprint(report: str | None) -> str | None:
    """Return an exact normalized duplicate key; missing reports have no key."""
    text = normalize_text(report)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def scanner_fingerprint(fields: Mapping[str, str | None]) -> str | None:
    """Hash caller-selected fields as a proxy, never as a verified patient/site ID.

    Empty values are omitted. Structured JSON prevents delimiter ambiguity;
    sorting makes mapping insertion order irrelevant. Field names are literal,
    so callers must apply one consistent schema to the entire cohort.
    """
    if not isinstance(fields, Mapping):
        raise ValueError("Scanner fields must be a mapping")
    values = []
    for name, raw_value in fields.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Scanner field names must be nonempty strings")
        value = normalize_text(raw_value)
        if value:
            values.append((name, value))
    if not values:
        return None
    payload = json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_records(records: Sequence[Record]) -> None:
    seen = set()
    for record in records:
        if not isinstance(record, Record):
            raise ValueError("Every observation must be a Record")
        if not isinstance(record.record_id, str) or not record.record_id.strip():
            raise ValueError("Record IDs must be nonempty strings")
        if record.record_id in seen:
            raise ValueError("Record IDs must be unique")
        seen.add(record.record_id)


def build_components(records: Sequence[Record]) -> Grouping:
    """Join each matching relation, including chains that mix both relations."""
    _validate_records(records)
    parent = {record.record_id: record.record_id for record in records}

    def find(value: str) -> str:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != value:
            next_value = parent[value]
            parent[value] = root
            value = next_value
        return root

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            keep, merge = sorted((left_root, right_root))
            parent[merge] = keep

    report_keys = {r.record_id: report_fingerprint(r.report) for r in records}
    scanner_keys = {r.record_id: scanner_fingerprint(r.scanner) for r in records}
    # Separate namespaces: a report hash must not match a scanner hash by accident.
    for relation in (report_keys, scanner_keys):
        first_by_key: dict[str, str] = {}
        for record_id in sorted(relation):
            key = relation[record_id]
            if key is not None:
                previous = first_by_key.setdefault(key, record_id)
                union(record_id, previous)

    members: dict[str, list[str]] = defaultdict(list)
    for record_id in sorted(parent):
        members[find(record_id)].append(record_id)
    components = tuple(sorted(tuple(group) for group in members.values()))
    return Grouping(components, report_keys, scanner_keys)


def _validate_fold_count(n_folds: int) -> None:
    if isinstance(n_folds, bool) or not isinstance(n_folds, int) or n_folds < 2:
        raise ValueError("At least two folds are required")


def assign_folds(records: Sequence[Record], n_folds: int = 3) -> dict[str, int]:
    """Greedily balance complete components, with deterministic ID-based ties.

    Returns record-level assignments for private in-memory use. This splitter
    does not stratify labels and is not scikit-learn's GroupKFold implementation.
    """
    _validate_fold_count(n_folds)
    grouping = build_components(records)
    if len(grouping.components) < n_folds:
        raise ValueError("Fewer connected components than requested folds")
    fold_sizes = [0] * n_folds
    assignments = {}
    for component in sorted(grouping.components, key=lambda c: (-len(c), c)):
        fold = min(range(n_folds), key=lambda f: (fold_sizes[f], f))
        for record_id in component:
            assignments[record_id] = fold
        fold_sizes[fold] += len(component)
    return assignments


def audit_folds(
    records: Sequence[Record], assignments: Mapping[str, int], n_folds: int
) -> dict:
    """Return aggregate overlap counts for a proposed validation-fold assignment.

    A component assigned to multiple validation folds causes train/validation
    overlap in ordinary K-fold evaluation. Errors never include input IDs/values.
    """
    _validate_fold_count(n_folds)
    grouping = build_components(records)
    if set(assignments) != set(grouping.report_keys):
        raise ValueError("Assignments must cover exactly the input records")
    for fold in assignments.values():
        if isinstance(fold, bool) or not isinstance(fold, int) or not 0 <= fold < n_folds:
            raise ValueError("Assignments contain an invalid fold number")
    if set(assignments.values()) != set(range(n_folds)):
        raise ValueError("Every fold must contain validation records")

    def crossing_groups(keys: Mapping[str, str | None]) -> int:
        folds_by_key: dict[str, set[int]] = defaultdict(set)
        for record_id, key in keys.items():
            if key is not None:
                folds_by_key[key].add(assignments[record_id])
        return sum(len(folds) > 1 for folds in folds_by_key.values())

    component_crossings = sum(
        len({assignments[record_id] for record_id in component}) > 1
        for component in grouping.components
    )
    histogram = Counter(len(component) for component in grouping.components)
    fold_counts = Counter(assignments.values())
    return {
        "records": len(records),
        "missing_reports": sum(key is None for key in grouping.report_keys.values()),
        "missing_scanners": sum(key is None for key in grouping.scanner_keys.values()),
        "report_groups": len({k for k in grouping.report_keys.values() if k is not None}),
        "scanner_groups": len({k for k in grouping.scanner_keys.values() if k is not None}),
        "connected_components": len(grouping.components),
        "largest_component_records": max(histogram, default=0),
        "component_size_histogram": {str(size): histogram[size] for size in sorted(histogram)},
        "report_groups_crossing_folds": crossing_groups(grouping.report_keys),
        "scanner_groups_crossing_folds": crossing_groups(grouping.scanner_keys),
        "components_crossing_folds": component_crossings,
        "folds": [
            {
                "fold": fold,
                "validation_records": fold_counts[fold],
                "training_records": len(records) - fold_counts[fold],
                "validation_components": sum(
                    {assignments[record_id] for record_id in component} == {fold}
                    for component in grouping.components
                ),
            }
            for fold in range(n_folds)
        ],
    }


def require_no_leakage(summary: Mapping) -> None:
    """Reject structural overlap; success makes no statistical performance claim."""
    names = (
        "report_groups_crossing_folds",
        "scanner_groups_crossing_folds",
        "components_crossing_folds",
    )
    if any(summary[name] != 0 for name in names):
        raise ValueError("At least one known relation crosses validation folds")


def load_records(path: Path) -> list[Record]:
    """Load explicit JSON records; there is no dataset discovery or DICOM adapter."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Cannot read the input as UTF-8 JSON") from error
    if not isinstance(payload, list):
        raise ValueError("Input must be a JSON list")
    records = []
    for row in payload:
        if not isinstance(row, dict) or set(row) != {"record_id", "report", "scanner"}:
            raise ValueError("Each row requires only record_id, report and scanner fields")
        records.append(Record(row["record_id"], row["report"], row["scanner"]))
    build_components(records)  # Reject malformed input before attempting a split.
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--demo", action="store_true", help="Use the bundled fictitious records")
    inputs.add_argument("--input", type=Path, help="Locally authorized JSON records")
    parser.add_argument("--folds", type=int, default=3)
    args = parser.parse_args(argv)
    path = Path(__file__).parent / "examples" / "synthetic_records.json" if args.demo else args.input
    try:
        records = load_records(path)
        assignments = assign_folds(records, args.folds)
        summary = audit_folds(records, assignments, args.folds)
        require_no_leakage(summary)
    except ValueError as error:
        parser.exit(2, f"Audit error: {error}\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: no known report/scanner component crosses validation folds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
