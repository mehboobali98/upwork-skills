#!/usr/bin/env python3
"""Tests for miniyaml.py. Run with: python3 test_miniyaml.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import miniyaml  # noqa: E402

RULES = """
rules:
  - id: low-hire-rate
    kind: fixed
    check:
      all:
        - [client_jobs_posted, ">=", 10]
        - [client_hire_rate, "<", 30]
    effect: SKIP
    reason: "A client who posts often and rarely hires isn't working the post."
    override:
      check: [client_hires, ">=", 100]
  - id: coaching-ask
    kind: judgement
    fires_when: true
"""


class Structure(unittest.TestCase):
    def test_rules_document(self):
        first, second = miniyaml.loads(RULES)["rules"]
        self.assertEqual(first["check"], {"all": [["client_jobs_posted", ">=", 10], ["client_hire_rate", "<", 30]]})
        self.assertEqual(first["override"], {"check": ["client_hires", ">=", 100]})
        self.assertEqual(first["reason"], "A client who posts often and rarely hires isn't working the post.")
        self.assertEqual(second, {"id": "coaching-ask", "kind": "judgement", "fires_when": True})

    def test_list_at_the_same_indent_as_its_key(self):
        data = miniyaml.loads("lanes:\n- name: rails\n  skills: [Ruby on Rails]\n- name: agent\nlog: csv\n")
        self.assertEqual(data, {"lanes": [{"name": "rails", "skills": ["Ruby on Rails"]}, {"name": "agent"}], "log": "csv"})

    def test_nested_list_inside_a_list_item(self):
        data = miniyaml.loads("a:\n  - x: 1\n    ys:\n      - 2\n      - 3\n  - x: 4\n")
        self.assertEqual(data, {"a": [{"x": 1, "ys": [2, 3]}, {"x": 4}]})

    def test_empty_values(self):
        self.assertEqual(miniyaml.loads(""), {})
        self.assertEqual(miniyaml.loads("# only a comment\n"), {})
        self.assertEqual(miniyaml.loads("a:\nb: []\nc: {}\n"), {"a": None, "b": [], "c": {}})


class Scalars(unittest.TestCase):
    def test_types(self):
        data = miniyaml.loads(
            "i: 30\nf: 4.8\nneg: -2\nt: true\nT: True\nn: null\ntilde: ~\ns: Pakistan\n"
            "id: \"1234567890123456789\"\ndate: 2026-11-01\nyes_word: yes\npath: ~/Office/x\n")
        self.assertEqual(data, {
            "i": 30, "f": 4.8, "neg": -2, "t": True, "T": True, "n": None, "tilde": None,
            "s": "Pakistan", "id": "1234567890123456789", "date": "2026-11-01",
            "yes_word": "yes", "path": "~/Office/x"})

    def test_quotes(self):
        data = miniyaml.loads("a: \"say \\\"hi\\\": now\"\nb: 'it''s'\nc: \"# not a comment\"\n")
        self.assertEqual(data, {"a": 'say "hi": now', "b": "it's", "c": "# not a comment"})

    def test_inline_lists(self):
        data = miniyaml.loads('a: [Claude Code, "Model Context Protocol (MCP)", "x, y", 3, ">="]\n')
        self.assertEqual(data["a"], ["Claude Code", "Model Context Protocol (MCP)", "x, y", 3, ">="])

    def test_comments(self):
        data = miniyaml.loads("# heading\na: 1  # trailing\nb: C#sharp\nc: 'quoted # kept'\n")
        self.assertEqual(data, {"a": 1, "b": "C#sharp", "c": "quoted # kept"})


class Errors(unittest.TestCase):
    def assertRejects(self, text, line, fragment):
        with self.assertRaises(miniyaml.YamlError) as caught:
            miniyaml.loads(text)
        self.assertIn(f"line {line}", str(caught.exception))
        self.assertIn(fragment, str(caught.exception))

    def test_tab_indent(self):
        self.assertRejects("a:\n\tb: 1\n", 2, "tabs")

    def test_outside_the_subset(self):
        self.assertRejects("a: &anchor 1\n", 1, "subset")
        self.assertRejects("a: |\n  text\n", 1, "subset")
        self.assertRejects("a: {b: 1}\n", 1, "subset")
        self.assertRejects("a: [[1, 2]]\n", 1, "nested")

    def test_unquoted_colon_in_a_value(self):
        self.assertRejects("reason: two checks: a and b\n", 1, "quote")

    def test_duplicate_key(self):
        self.assertRejects("a: 1\na: 2\n", 2, "duplicate")

    def test_bad_indentation(self):
        self.assertRejects("a:\n  b: 1\n    c: 2\n", 3, "indentation")
        self.assertRejects("a:\n    b: 1\n  c: 2\n", 3, "indentation")

    def test_unterminated_quote(self):
        self.assertRejects('a: "open\n', 1, "unterminated")

    def test_item_where_a_key_belongs(self):
        self.assertRejects("a: 1\n- b\n", 2, "list item")

    def test_first_line_offset(self):
        with self.assertRaises(miniyaml.YamlError) as caught:
            miniyaml.loads("a: 1\na: 2\n", first_line=2)
        self.assertIn("line 3", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
