"""Name the connector tools a scheduled routine run must not have.

    routine_tools.py --connection NAME TOOLS_FILE

TOOLS_FILE lists every tool the connector exposes, one per line, as this
session names them (for example mcp__claude_ai_Upwork__upwork__find_jobs).
Prints a JSON list of the cloud names, mcp__<NAME>__<tool>, of every tool
that rules/routine-tools.yaml doesn't allow for that connector. They go in
the routine's disallowed_tools; a tool left off stays callable.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import miniyaml  # noqa: E402

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TOOLS = os.path.join(PLUGIN_ROOT, "rules", "routine-tools.yaml")
CONNECTION = re.compile(r"^[A-Za-z0-9_-]+$")


class ToolsError(ValueError):
    pass


def load_allowed(path=DEFAULT_TOOLS):
    with open(path, encoding="utf-8") as fh:
        data = miniyaml.loads(fh.read())
    entries = data.get("connectors") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ToolsError(f"{path}: expected a 'connectors' list")
    for entry in entries:
        if not (isinstance(entry, dict) and entry.get("name") and entry.get("match")
                and isinstance(entry.get("allow"), list)):
            raise ToolsError(f"{path}: every connector needs a name, a match and an allow list")
    return entries


def entry_for(connection, entries):
    for entry in entries:
        if entry["match"].lower() in connection.lower():
            return entry
    raise ToolsError(f"no entry in routine-tools.yaml matches the connection {connection!r}")


def server_tool(local_name):
    parts = local_name.strip().split("__")
    if len(parts) < 3 or parts[0] != "mcp" or not all(parts):
        raise ToolsError(f"{local_name!r} isn't an MCP tool name like mcp__server__tool")
    return "__".join(parts[2:])


def deny_list(connection, local_names, allow):
    """Return (cloud names to deny, allowed tools the connector didn't list)."""
    if not CONNECTION.match(connection):
        raise ToolsError(f"connection name {connection!r} may use only letters, digits, _ and -")
    tools = {server_tool(name) for name in local_names if name.strip()}
    deny = sorted(f"mcp__{connection}__{t}" for t in tools if t.split("__")[-1] not in allow)
    seen = {t.split("__")[-1] for t in tools}
    return deny, [a for a in allow if a not in seen]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the tools a routine run must not have.")
    ap.add_argument("--connection", required=True, help="the connector's name on the routine, e.g. Upwork")
    ap.add_argument("tools_file", help="every tool the connector exposes, one per line")
    ap.add_argument("--allowed", default=DEFAULT_TOOLS)
    args = ap.parse_args(argv)
    try:
        allow = entry_for(args.connection, load_allowed(args.allowed))["allow"]
        with open(args.tools_file, encoding="utf-8") as fh:
            deny, missing = deny_list(args.connection, fh.read().splitlines(), allow)
    except (OSError, ValueError) as e:
        print(f"routine_tools: {e}", file=sys.stderr)
        return 2
    for name in missing:
        print(f"routine_tools: {name} is allowed but wasn't in the list; check the connector", file=sys.stderr)
    print(json.dumps(deny, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
