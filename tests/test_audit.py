"""All inputs are invented; no dataset, network or third-party package is used."""

from collections import deque
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import unittest

from mri_validation_audit import (
    Record,
    assign_folds,
    audit_folds,
    build_components,
    load_records,
    normalize_text,
    report_fingerprint,
    require_no_leakage,
    scanner_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]


def toy_records():
    return [
        Record("A", "report alpha", {"device": "one"}),
        Record("B", " REPORT ALPHA ", {"device": "two"}),
        Record("C", "report beta", {"device": "TWO"}),
        Record("D", None, {}),
        Record("E", " \n ", {"device": None}),
    ]


def graph_components(labels):
    """Independent all-pairs graph/BFS oracle on latent synthetic group labels."""
    remaining = set(range(len(labels)))
    result = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = deque([start])
        members = [start]
        while queue:
            left = queue.popleft()
            for right in sorted(remaining):
                a_report, a_scanner = labels[left]
                b_report, b_scanner = labels[right]
                if (a_report is not None and a_report == b_report) or (
                    a_scanner is not None and a_scanner == b_scanner
                ):
                    remaining.remove(right)
                    members.append(right)
                    queue.append(right)
        result.append(tuple(sorted(f"toy-{i:02d}" for i in members)))
    return tuple(sorted(result))


class FingerprintTests(unittest.TestCase):
    def test_unicode_case_whitespace_normalization(self):
        self.assertEqual(normalize_text("  ＦＵＬＬ\n  Case\tText "), "full case text")
        self.assertEqual(report_fingerprint("  ＦＵＬＬ\n  Case\tText "),
                         report_fingerprint("full case text"))
        self.assertNotEqual(report_fingerprint("alpha"), report_fingerprint("alpha."))

    def test_missing_values_have_no_fingerprint(self):
        for value in (None, "", " \n\t "):
            self.assertIsNone(report_fingerprint(value))
        for fields in ({}, {"a": None}, {"a": " \n "}):
            self.assertIsNone(scanner_fingerprint(fields))

    def test_scanner_order_normalization_and_missing_values(self):
        left = {"family": " ＡＬＰＨＡ ", "protocol": "T1  toy", "missing": None}
        right = {"protocol": "t1 toy", "family": "alpha"}
        self.assertEqual(scanner_fingerprint(left), scanner_fingerprint(right))
        self.assertNotEqual(scanner_fingerprint({"device": "one"}),
                            scanner_fingerprint({"protocol": "one"}))

    def test_structured_serialization_avoids_separator_ambiguity(self):
        self.assertNotEqual(
            scanner_fingerprint({"a": "x\x1fb=y", "b": "z"}),
            scanner_fingerprint({"a": "x", "b": "y\x1fb=z"}),
        )

    def test_invalid_field_types_are_rejected(self):
        for report in (float("nan"), 2, [], {}):
            with self.subTest(report_type=type(report).__name__), self.assertRaises(ValueError):
                report_fingerprint(report)
        for scanner in (None, [], {"": "one"}, {2: "one"}, {"device": 3}):
            with self.subTest(scanner_type=type(scanner).__name__), self.assertRaises(ValueError):
                scanner_fingerprint(scanner)


class ComponentTests(unittest.TestCase):
    def test_mixed_chain_and_missing_singletons(self):
        grouping = build_components(toy_records())
        self.assertEqual(grouping.components, (("A", "B", "C"), ("D",), ("E",)))
        # A/C have neither a direct report match nor a direct scanner match.
        self.assertNotEqual(grouping.report_keys["A"], grouping.report_keys["C"])
        self.assertNotEqual(grouping.scanner_keys["A"], grouping.scanner_keys["C"])

    def test_duplicate_or_empty_ids_rejected_without_echoing_values(self):
        private = "PRIVATE_IDENTIFIER"
        with self.assertRaisesRegex(ValueError, "unique") as caught:
            build_components([Record(private, None, {}), Record(private, None, {})])
        self.assertNotIn(private, str(caught.exception))
        for record_id in (None, "", " \n ", 2):
            with self.subTest(record_id_type=type(record_id).__name__), self.assertRaises(ValueError):
                build_components([Record(record_id, None, {})])

    def test_input_permutation_preserves_components_and_folds(self):
        records = toy_records()
        expected = assign_folds(records, 3)
        randomizer = random.Random(17)
        for _ in range(20):
            randomizer.shuffle(records)
            self.assertEqual(build_components(records).components,
                             (("A", "B", "C"), ("D",), ("E",)))
            self.assertEqual(assign_folds(records, 3), expected)

    def test_randomized_components_match_independent_graph_oracle(self):
        randomizer = random.Random(20261001)
        for case in range(100):
            size = randomizer.randint(1, 30)
            labels = [
                (randomizer.choice([None, 0, 1, 2, 3, 4, 5]),
                 randomizer.choice([None, 0, 1, 2, 3, 4, 5]))
                for _ in range(size)
            ]
            records = [
                Record(f"toy-{i:02d}", None if r is None else f"  REPORT {r}  ",
                       {} if s is None else {"device": f"  TOY {s}  "})
                for i, (r, s) in enumerate(labels)
            ]
            with self.subTest(case=case):
                actual = build_components(records).components
                self.assertEqual(actual, graph_components(labels))
                if len(actual) >= 2:
                    n_folds = min(len(actual), 4)
                    assignment = assign_folds(records, n_folds)
                    require_no_leakage(audit_folds(records, assignment, n_folds))
                    randomizer.shuffle(records)
                    self.assertEqual(assign_folds(records, n_folds), assignment)


class FoldTests(unittest.TestCase):
    def test_every_record_is_assigned_once_and_components_stay_whole(self):
        records = toy_records()
        assignments = assign_folds(records, 3)
        self.assertEqual(set(assignments), {"A", "B", "C", "D", "E"})
        self.assertEqual(set(assignments.values()), {0, 1, 2})
        self.assertEqual({assignments[i] for i in ("A", "B", "C")}, {0})
        summary = audit_folds(records, assignments, 3)
        require_no_leakage(summary)
        self.assertEqual(summary["component_size_histogram"], {"1": 2, "3": 1})
        self.assertEqual(sum(f["validation_records"] for f in summary["folds"]), 5)

    def test_deliberate_mixed_chain_leak_is_detected(self):
        assignments = {"A": 0, "B": 1, "C": 2, "D": 0, "E": 1}
        summary = audit_folds(toy_records(), assignments, 3)
        self.assertEqual(summary["report_groups_crossing_folds"], 1)
        self.assertEqual(summary["scanner_groups_crossing_folds"], 1)
        self.assertEqual(summary["components_crossing_folds"], 1)
        with self.assertRaisesRegex(ValueError, "crosses"):
            require_no_leakage(summary)

    def test_invalid_fold_count_and_infeasible_split(self):
        for count in (0, 1, -1, True, 2.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                assign_folds(toy_records(), count)
        with self.assertRaisesRegex(ValueError, "Fewer connected components"):
            assign_folds(toy_records(), 4)
        with self.assertRaisesRegex(ValueError, "Fewer connected components"):
            assign_folds([], 2)

    def test_assignment_coverage_and_type_validation(self):
        valid = assign_folds(toy_records(), 3)
        for assignments in ({k: v for k, v in valid.items() if k != "A"},
                            dict(valid, extra=0), dict(valid, A=-1),
                            dict(valid, A=3), dict(valid, A=True), dict(valid, A=1.0)):
            with self.subTest(assignments=assignments), self.assertRaises(ValueError):
                audit_folds(toy_records(), assignments, 3)

    def test_fold_number_ties_and_uneven_component_sizes_are_visible(self):
        records = load_records(ROOT / "examples" / "synthetic_records.json")
        summary = audit_folds(records, assign_folds(records, 3), 3)
        self.assertEqual(summary["connected_components"], 6)
        self.assertEqual(summary["largest_component_records"], 3)
        self.assertEqual([f["validation_records"] for f in summary["folds"]], [4, 3, 3])
        self.assertEqual(summary["missing_reports"], 2)
        self.assertEqual(summary["missing_scanners"], 2)

    def test_audit_rejects_empty_cohort_and_empty_validation_folds(self):
        records = [Record("A", None, {}), Record("B", None, {})]
        for observations, assignments in (([], {}), (records, {"A": 0, "B": 0})):
            with self.subTest(record_count=len(observations)), self.assertRaisesRegex(
                ValueError, "Every fold must contain validation records"
            ):
                audit_folds(observations, assignments, 2)

    def test_audit_still_diagnoses_a_single_component_crossing_nonempty_folds(self):
        records = [Record("A", "shared report", {}), Record("B", "shared report", {})]
        summary = audit_folds(records, {"A": 0, "B": 1}, 2)
        self.assertEqual(summary["connected_components"], 1)
        self.assertEqual(summary["components_crossing_folds"], 1)
        with self.assertRaises(ValueError):
            require_no_leakage(summary)


class InputAndCLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "mri_validation_audit.py"), *args],
                              text=True, capture_output=True, check=False)

    def test_demo_cli_is_aggregate_only_and_reproducible(self):
        first = self.run_cli("--demo")
        second = self.run_cli("--demo")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        self.assertIn("PASS:", first.stdout)
        for forbidden in ("synthetic-", "Toy report", "toy-device-", "record_id"):
            self.assertNotIn(forbidden, first.stdout)
        self.assertIsNone(re.search(r"\b[a-f0-9]{64}\b", first.stdout))

    def test_json_cli_matches_demo(self):
        demo = self.run_cli("--demo")
        explicit = self.run_cli("--input", str(ROOT / "examples" / "synthetic_records.json"))
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(explicit.stdout, demo.stdout)

    def test_bad_json_and_extra_fields_do_not_echo_private_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.json"
            secret = "PRIVATE_VALUE_NOT_FOR_CLI"
            for payload in (
                "{broken",
                {"private": secret},
                [{"record_id": secret, "report": secret, "scanner": {}, "extra": secret}],
                [{"record_id": secret, "report": secret, "scanner": {"field": 7}}],
            ):
                path.write_text(payload if isinstance(payload, str) else json.dumps(payload),
                                encoding="utf-8")
                result = self.run_cli("--input", str(path))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn(secret, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_cli_infeasible_fold_request_is_clear(self):
        result = self.run_cli("--demo", "--folds", "7")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Fewer connected components", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
