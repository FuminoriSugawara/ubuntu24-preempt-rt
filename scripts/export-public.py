#!/usr/bin/env python3
"""公開対象の一覧を検証し、新規ディレクトリへ書き出す。"""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil


def export(destination: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    entries = (root / "PUBLIC-FILES.txt").read_text().splitlines()
    sources = []
    seen = set()
    for entry in entries:
        if not entry or entry.startswith("#"):
            continue
        relative = PurePosixPath(entry)
        if (relative.is_absolute() or ".." in relative.parts
                or str(relative) != entry or "\\" in entry
                or entry in seen or entry == "PUBLIC-SHA256SUMS"):
            raise ValueError(f"Invalid or duplicate path: {entry}")
        seen.add(entry)
        source = root / entry
        if any(part.is_symlink() for part in (source, *source.parents)
               if part != root and root in part.parents):
            raise ValueError(f"Symlinks are not allowed: {entry}")
        if not source.is_file() or not source.resolve().is_relative_to(root):
            raise ValueError(f"Missing or invalid file: {entry}")
        sources.append((entry, source))
    if not sources:
        raise ValueError("Public file list is empty")
    # すべての入力を検証した後に出力先を作成する。
    destination.mkdir(parents=True, exist_ok=False)
    checksums = []
    for entry, source in sources:
        target = destination / entry
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        checksums.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {entry}\n")
    (destination / "PUBLIC-SHA256SUMS").write_text("".join(checksums))
    print(f"Exported {len(sources)} files to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        export(args.destination)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Export failed: {error}\n")


if __name__ == "__main__":
    main()
