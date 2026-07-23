from __future__ import annotations

import argparse
from pathlib import Path


def export(case: str, checkpoint: Path, output: Path) -> None:
    raise NotImplementedError("implement phase-trajectory export")


def advance(case: str, checkpoint: Path, cycles: int, output: Path) -> None:
    raise NotImplementedError("implement checkpoint advancement")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--case", required=True)
    export_parser.add_argument("--checkpoint", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)

    advance_parser = subparsers.add_parser("advance")
    advance_parser.add_argument("--case", required=True)
    advance_parser.add_argument("--checkpoint", type=Path, required=True)
    advance_parser.add_argument("--cycles", type=int, required=True)
    advance_parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "export":
        export(args.case, args.checkpoint, args.output)
    else:
        if args.cycles < 1:
            raise ValueError("--cycles must be positive")
        advance(args.case, args.checkpoint, args.cycles, args.output)


if __name__ == "__main__":
    main()
