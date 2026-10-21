"""Mechanical checks on a cover letter or screening answer before it is sent.

    check_letter.py letter.txt [answer.txt ...] [--max-words N]
    check_letter.py - < letter.txt

Fails on an em dash, a spaced en dash standing in for one, an [ASK ...]
placeholder left in, or text over Upwork's 5,000-character limit. Prints each
file's word and character count either way.
"""
import argparse
import re
import sys

EM_DASH = "\u2014"
SPACED_EN_DASH = " \u2013 "
LIMIT = 5000
ASK = re.compile(r"\[ASK[^\]]*\]")


def problems(text, max_words=None):
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        if EM_DASH in line:
            found.append(f"line {n}: em dash")
        if SPACED_EN_DASH in line:
            found.append(f"line {n}: en dash used as a dash")
        found += [f"line {n}: unresolved {marker}" for marker in ASK.findall(line)]
    if len(text) > LIMIT:
        found.append(f"{len(text)} characters, over Upwork's {LIMIT}")
    words = len(text.split())
    if max_words and words > max_words:
        found.append(f"{words} words, over the {max_words} asked for")
    return found


def _read(name):
    if name == "-":
        return sys.stdin.read().strip()
    with open(name, encoding="utf-8") as fh:
        return fh.read().strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check proposal text before it is sent.")
    ap.add_argument("files", nargs="+", help="text files, or - for stdin")
    ap.add_argument("--max-words", type=int)
    args = ap.parse_args(argv)
    failed = False
    for name in args.files:
        try:
            text = _read(name)
        except OSError as e:
            print(f"check_letter: {e}", file=sys.stderr)
            return 2
        found = problems(text, args.max_words)
        print(f"{name}: words {len(text.split())}, characters {len(text)}")
        for problem in found:
            print(f"  {problem}")
        failed = failed or bool(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
