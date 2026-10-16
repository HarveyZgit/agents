#!/usr/bin/env python3
"""同步独立 resume 包资源；--check 只检查，不导入或执行 reader。"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "skills"
FILES = (
    "scripts/session_reader.py",
    "references/CORE.md",
    "references/formats.md",
    "references/PROVENANCE.md",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift = []
    for relative in FILES:
        source = ROOT / "resume-claude" / relative
        if source.is_symlink() or not source.is_file():
            parser.error(f"canonical resource missing or symlink: {source}")
        data = source.read_bytes()
        for name in ("resume-codex", "resume-cursor"):
            target = ROOT / name / relative
            if target.is_symlink():
                parser.error(f"destination must not be a symlink: {target}")
            if target.is_file() and target.read_bytes() == data:
                continue
            drift.append(str(target.relative_to(ROOT)))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    if drift:
        print(("资源不同步：" if args.check else "已同步：") + "\n" + "\n".join(drift))
    else:
        print("三个独立 resume 包资源一致。")
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
