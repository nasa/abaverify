"""Check result cardinality without requiring the Abaqus solver.

Modification by Sylvester Kaczmarek, 2026-09-26, derived from NASA Abaverify.
Distributed under the NASA Open Source Agreement in LICENSE.txt.
"""

import copy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from abaverify import main


class ResultLengthTests(unittest.TestCase):
    def check_results(self, records):
        with TemporaryDirectory() as output_dir:
            job_name = "result_length_" + uuid4().hex
            module_name = job_name + "_results"
            path = Path(output_dir, module_name + ".py")
            path.write_text("results = " + repr(records), encoding="utf-8")
            original = path.read_bytes()
            options = SimpleNamespace(outputDirectory=output_dir)
            try:
                with (
                    patch.object(main, "options", options, create=True),
                    patch.object(sys, "path", sys.path.copy()),
                ):
                    main.TestCase()._runAssertionsOnResults(job_name, None, None)
            finally:
                sys.modules.pop(module_name, None)
                self.assertEqual(path.read_bytes(), original)

    def test_incomplete_sequences_fail_instead_of_passing(self):
        for computed, reference, tolerance in (
            ([], [1.0], [0.1]),
            ([1.0], [1.0, 2.0], [0.1, 0.1]),
            ((), (1.0, 2.0), (0.1, 0.1)),
            ([], [(1.0, 2.0)], (0.1, 0.1)),
            ([(1.0, 2.0)], [(1.0, 2.0), (3.0, 4.0)], (0.1, 0.1)),
        ):
            with self.subTest(computed=computed, reference=reference):
                with self.assertRaisesRegex(AssertionError, "same length"):
                    self.check_results(
                        [
                            {
                                "computedValue": computed,
                                "referenceValue": reference,
                                "tolerance": tolerance,
                            }
                        ]
                    )

    def test_extra_computed_values_fail_with_a_length_assertion(self):
        for computed, reference, tolerance in (
            ([1.0], [], [0.1]),
            ([1.0, 2.0], [1.0], [0.1, 0.1]),
            ([(1.0, 2.0), (3.0, 4.0)], [(1.0, 2.0)], (0.1, 0.1)),
        ):
            with self.subTest(computed=computed, reference=reference):
                with self.assertRaisesRegex(AssertionError, "same length"):
                    self.check_results(
                        [
                            {
                                "computedValue": computed,
                                "referenceValue": reference,
                                "tolerance": tolerance,
                            }
                        ]
                    )

    def test_matching_sequences_keep_the_existing_tolerance_rules(self):
        for computed, reference, tolerance in (
            ([], [], []),
            ([1.05, 2.05], [1.0, 2.0], [0.1, 0.1]),
            ((1.05, 2.05), (1.0, 2.0), (0.1, 0.1)),
            ([(1.05, 2.05), (3.05, 4.05)], [(1.0, 2.0), (3.0, 4.0)], (0.1, 0.1)),
            (
                [(1.05, 2.05), (3.05, 4.05)],
                [(1.0, 2.0), (3.0, 4.0)],
                [(0.1, 0.1), (0.1, 0.1)],
            ),
        ):
            with self.subTest(computed=computed):
                self.check_results(
                    [
                        {
                            "computedValue": computed,
                            "referenceValue": reference,
                            "tolerance": tolerance,
                        }
                    ]
                )

    def test_matching_lengths_still_reject_incorrect_values(self):
        for record in (
            {"computedValue": [1.5], "referenceValue": [1.0], "tolerance": [0.1]},
            {
                "computedValue": [(1.0, 2.5)],
                "referenceValue": [(1.0, 2.0)],
                "tolerance": (0.1, 0.1),
            },
            {
                "computedValue": [(1.0,)],
                "referenceValue": [(1.0, 2.0)],
                "tolerance": (0.1, 0.1),
            },
        ):
            with self.subTest(record=record):
                with self.assertRaises(AssertionError):
                    self.check_results([record])

    def test_later_incomplete_result_is_not_hidden_by_a_passing_result(self):
        first = {"computedValue": 2.0, "referenceValue": 2.0}
        missing = {"computedValue": [], "referenceValue": [5.0], "tolerance": [0.1]}
        for records in ([first, missing], [missing, first]):
            with self.subTest(records=records):
                original = copy.deepcopy(records)
                with self.assertRaisesRegex(AssertionError, "same length"):
                    self.check_results(records)
                self.assertEqual(records, original)

    def test_scalar_results_are_unchanged(self):
        self.check_results(
            [
                {"computedValue": 1.0, "referenceValue": 1.0},
                {"computedValue": 1.05, "referenceValue": 1.0, "tolerance": 0.1},
            ]
        )
        with self.assertRaises(AssertionError):
            self.check_results([{"computedValue": 2.0, "referenceValue": 1.0}])

    def test_unittest_records_an_incomplete_result_as_a_failure(self):
        records = [{"computedValue": [], "referenceValue": [1.0], "tolerance": [0.1]}]
        suite = unittest.TestSuite(
            [unittest.FunctionTestCase(lambda: self.check_results(records))]
        )
        result = unittest.TestResult()
        suite.run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.errors, [])
        self.assertIn("same length", result.failures[0][1])

    def test_custom_assertion_callback_is_unchanged(self):
        callback = Mock()
        case = main.TestCase()
        with patch.object(
            main, "options", SimpleNamespace(outputDirectory="unused"), create=True
        ):
            case._runAssertionsOnResults("custom_job", callback, ["argument"])
        callback.assert_called_once_with(case, "custom_job", ["argument"])


if __name__ == "__main__":
    unittest.main()
