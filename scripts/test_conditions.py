#!/usr/bin/env python3
"""Tests for conditions.py. Run with: python3 test_conditions.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conditions  # noqa: E402


class Evaluate(unittest.TestCase):
    def test_check(self):
        self.assertEqual(conditions.evaluate(["a", ">=", 10], {"a": 12}), (True, ["a 12 >= 10"]))
        self.assertIs(conditions.evaluate(["a", "<", 30], {"a": 63})[0], False)

    def test_unknown_fact(self):
        self.assertEqual(conditions.evaluate(["a", "==", 0], {"a": None}), (None, ["a unknown"]))
        self.assertEqual(conditions.evaluate(["a", "==", 0], {}), (None, ["a unknown"]))

    def test_reference(self):
        self.assertIs(conditions.evaluate(["cost", ">", "$balance"], {"cost": 27, "balance": 20})[0], True)
        self.assertEqual(conditions.evaluate(["cost", ">", "$balance"], {"cost": 27, "balance": None}),
                         (None, ["balance unknown"]))

    def test_mismatched_types_are_unknown(self):
        self.assertIsNone(conditions.evaluate(["a", "<", 3], {"a": "x"})[0])

    def test_all_and_any(self):
        f = {"t": 1, "f": 0, "u": None}
        yes, no, unknown = ["t", "==", 1], ["f", "==", 1], ["u", "==", 1]
        cases = [
            ("all", [yes, yes], True), ("all", [yes, no], False),
            ("all", [unknown, no], False), ("all", [yes, unknown], None),
            ("any", [no, yes], True), ("any", [unknown, yes], True),
            ("any", [no, unknown], None), ("any", [no, no], False),
        ]
        for key, parts, want in cases:
            self.assertIs(conditions.evaluate({key: parts}, f)[0], want, (key, parts))

    def test_numbers_are_shown_plainly(self):
        self.assertEqual(conditions.evaluate(["s", "==", 0], {"s": 0.0})[1], ["s 0 == 0"])
        self.assertEqual(conditions.evaluate(["s", ">", 1], {"s": 4436.24})[1], ["s 4436.24 > 1"])
        self.assertEqual(conditions.evaluate(["b", "==", True], {"b": True})[1], ["b true == true"])


class Validate(unittest.TestCase):
    def test_accepts(self):
        conditions.validate({"all": [["a", "==", 1], {"any": [["b", "<", "$c"]]}]}, "rule", {"a", "b", "c"})

    def test_rejects(self):
        bad = [
            ["a", "=", 1], ["a", "=="], {"all": []}, {"none": [["a", "==", 1]]}, "a == 1",
            {"all": [["a", "==", 1]], "any": [["a", "==", 1]]},
        ]
        for cond in bad:
            with self.assertRaises(conditions.ConditionError, msg=cond):
                conditions.validate(cond, "rule", {"a"})

    def test_unknown_fact_names(self):
        with self.assertRaises(conditions.ConditionError) as caught:
            conditions.validate(["clinet_hires", "==", 0], "rule x.check", {"client_hires"})
        self.assertIn("clinet_hires", str(caught.exception))
        with self.assertRaises(conditions.ConditionError):
            conditions.validate(["client_hires", "<", "$floor"], "rule", {"client_hires"})


if __name__ == "__main__":
    unittest.main()
