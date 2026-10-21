"""Read the subset of YAML that upwork-skills profiles and rules are written in.

    data = miniyaml.loads(text)

Block mappings and sequences, plain and quoted scalars, inline lists of
scalars, and comments. Stdlib only, so the scripts run on the python3 macOS
ships. Anything outside the subset raises YamlError naming the line, rather
than being read some other way.
"""
import re

KEY = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.\- ]*?)\s*:(?:\s+(.*))?$")
INT = re.compile(r"^[-+]?\d+$")
FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?$")
NULLS = {"null", "Null", "NULL", "~"}
TRUES = {"true", "True", "TRUE"}
FALSES = {"false", "False", "FALSE"}
ESCAPES = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t"}
RESERVED = "&*!|>%@`{"


class YamlError(ValueError):
    pass


def loads(text, first_line=1):
    lines = _lines(text, first_line)
    if not lines:
        return {}
    value, i = _block(lines, 0, lines[0][0])
    if i < len(lines):
        raise YamlError(f"line {lines[i][2]}: doesn't fit the structure above it")
    return value


def _lines(text, first_line):
    out = []
    for n, raw in enumerate(text.splitlines(), first_line):
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        lead = body[: len(body) - len(body.lstrip())]
        if "\t" in lead:
            raise YamlError(f"line {n}: indent with spaces, not tabs")
        out.append((len(lead), body.strip(), n))
    return out


def _strip_comment(line):
    quote, i = None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or line[i - 1] in " [,"):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
        i += 1
    return line


def _is_item(content):
    return content == "-" or content.startswith("- ")


def _block(lines, i, indent):
    if _is_item(lines[i][1]):
        return _sequence(lines, i, indent)
    return _mapping(lines, i, indent)


def _mapping(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        _, content, n = lines[i]
        if _is_item(content):
            raise YamlError(f"line {n}: list item where a key was expected")
        match = KEY.match(content)
        if not match:
            raise YamlError(f"line {n}: expected 'key: value'")
        key, rest = match.group(1), match.group(2)
        if key in out:
            raise YamlError(f"line {n}: duplicate key {key!r}")
        i += 1
        if rest is not None:
            out[key] = _scalar(rest, n)
        elif i < len(lines) and (lines[i][0] > indent or (lines[i][0] == indent and _is_item(lines[i][1]))):
            out[key], i = _block(lines, i, lines[i][0])
        else:
            out[key] = None
    _no_deeper(lines, i, indent)
    return out, i


def _sequence(lines, i, indent):
    out = []
    while i < len(lines) and lines[i][0] == indent and _is_item(lines[i][1]):
        _, content, n = lines[i]
        rest = content[1:].lstrip()
        if not rest:
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                item, i = _block(lines, i, lines[i][0])
            else:
                item = None
        elif KEY.match(rest):
            child = indent + len(content) - len(rest)
            lines[i] = (child, rest, n)
            item, i = _mapping(lines, i, child)
        else:
            item, i = _scalar(rest, n), i + 1
        out.append(item)
    _no_deeper(lines, i, indent)
    return out, i


def _no_deeper(lines, i, indent):
    if i < len(lines) and lines[i][0] > indent:
        raise YamlError(f"line {lines[i][2]}: unexpected indentation")


def _scalar(text, n):
    if text[0] == '"':
        return _double_quoted(text, n)
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'":
            raise YamlError(f"line {n}: unterminated quote")
        return text[1:-1].replace("''", "'")
    if text[0] == "[":
        return _inline_list(text, n)
    if text == "{}":
        return {}
    if text[0] in RESERVED or text.startswith("- "):
        raise YamlError(f"line {n}: {text[:12]!r} is outside the supported YAML subset")
    if ": " in text:
        raise YamlError(f"line {n}: quote a value that contains ': '")
    return _plain(text)


def _plain(text):
    if text in NULLS:
        return None
    if text in TRUES:
        return True
    if text in FALSES:
        return False
    if INT.match(text):
        return int(text)
    if FLOAT.match(text):
        return float(text)
    return text


def _double_quoted(text, n):
    out, i = [], 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text) or text[i + 1] not in ESCAPES:
                raise YamlError(f"line {n}: unsupported escape in a quoted string")
            out.append(ESCAPES[text[i + 1]])
            i += 2
            continue
        if ch == '"':
            if text[i + 1:].strip():
                raise YamlError(f"line {n}: text after the closing quote")
            return "".join(out)
        out.append(ch)
        i += 1
    raise YamlError(f"line {n}: unterminated quote")


def _inline_list(text, n):
    if text[-1] != "]":
        raise YamlError(f"line {n}: unterminated inline list")
    inner = text[1:-1].strip()
    if not inner:
        return []
    items, buf, quote, i = [], "", None, 0
    while i < len(inner):
        ch = inner[i]
        if quote:
            buf += ch
            if ch == "\\" and quote == '"' and i + 1 < len(inner):
                buf += inner[i + 1]
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'" and not buf.strip():
            quote = ch
            buf += ch
        elif ch == ",":
            items.append(buf.strip())
            buf = ""
        elif ch in "[]{}":
            raise YamlError(f"line {n}: nested inline lists or mappings are not supported")
        else:
            buf += ch
        i += 1
    if quote:
        raise YamlError(f"line {n}: unterminated quote")
    items.append(buf.strip())
    if not all(items):
        raise YamlError(f"line {n}: empty item in an inline list")
    return [_scalar(item, n) for item in items]
