#!/usr/bin/env python3
"""Tests for check_letter.py. Run with: python3 test_check_letter.py"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_letter  # noqa: E402

EM, EN = "\u2014", "\u2013"


class Problems(unittest.TestCase):
    def test_clean_text_passes(self):
        self.assertEqual(check_letter.problems(f"Hi Sam,\n\nThe upgrade takes 2{EN}3 evenings."), [])

    def test_dashes(self):
        found = check_letter.problems(f"First line\nIt works {EM} mostly.\nAnd this {EN} too.")
        self.assertEqual(found, ["line 2: em dash", "line 3: en dash used as a dash"])

    def test_ask_markers(self):
        self.assertEqual(check_letter.problems("Rate: [ASK SAM: rate]"), ["line 1: unresolved [ASK SAM: rate]"])

    def test_limits(self):
        self.assertEqual(check_letter.problems("a" * 5000), [])
        self.assertEqual(check_letter.problems("a" * 5001), ["5001 characters, over Upwork's 5000"])
        self.assertEqual(check_letter.problems("one two three", max_words=2), ["3 words, over the 2 asked for"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_exit_codes(self):
        good, bad = self.write("good.txt", "Plain text.\n"), self.write("bad.txt", f"Bad {EM} text.\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_letter.main([good]), 0)
            self.assertEqual(check_letter.main([good, bad]), 1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_letter.main([os.path.join(self.dir, "missing.txt")]), 2)

    def test_stdin(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("Fine.\n")), contextlib.redirect_stdout(out):
            self.assertEqual(check_letter.main(["-"]), 0)
        self.assertEqual(out.getvalue(), "-: words 1, characters 5\n")


if __name__ == "__main__":
    unittest.main()
