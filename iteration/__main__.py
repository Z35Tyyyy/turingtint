"""CLI for the bounded evidence loop."""

import argparse
import json
import sys
from pathlib import Path

from .runner import ProtocolError, run, status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded local checks and track unresolved release gates.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "status", "open-issues"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd())
        command.add_argument("--state-dir", type=Path, default=Path(".iteration"))
        if name == "run":
            command.add_argument("--protocol", type=Path, required=True)
            command.add_argument("--reviews", type=Path)
            command.add_argument("--max-iterations", type=int, default=1)
            command.add_argument("--max-seconds", type=float, default=120)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    state_dir = root / arguments.state_dir
    try:
        if arguments.command == "run":
            value = run(root, root / arguments.protocol, state_dir, max_iterations=arguments.max_iterations, max_seconds=arguments.max_seconds, reviews_path=root / arguments.reviews if arguments.reviews else None)
        else:
            value = status(state_dir)
            if arguments.command == "open-issues":
                value = value["open_issues"]
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 1 if arguments.command == "run" and value["decision"] == "block" else 0
    except (ProtocolError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
