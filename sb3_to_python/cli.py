from __future__ import annotations

import argparse
from pathlib import Path

from .converter import ScratchToPythonConverter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sb3_to_python",
        description="Convert Scratch/PenguinMod .sb3 files into a readable Python draft",
    )
    parser.add_argument("source", nargs="?", help="Path to .sb3 source file")
    parser.add_argument("-o", "--output", help="Output .py file path")
    parser.add_argument(
        "-t",
        "--target-index",
        type=int,
        help="Convert only one target by index. By default the whole project is converted.",
    )
    parser.add_argument(
        "--single-target",
        action="store_true",
        help="Shortcut: convert only the target selected by --target-index.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.source:
        parser.print_help()
        return 1

    loaded = ScratchToPythonConverter.load_sb3(args.source)
    converter = ScratchToPythonConverter(loaded.project_json)

    if args.single_target or args.target_index is not None:
        python_code = converter.convert_current_target(args.target_index or 0)
    else:
        python_code = converter.convert_project()

    output = Path(args.output) if args.output else Path(args.source).with_suffix(".py")
    output.write_text(python_code, encoding="utf-8")
    print(f"Written: {output}")
    return 0
