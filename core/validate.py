#!/usr/bin/env python
"""Report every unverified (status: ASK) field in the profile.

Fact-lock rule: an ASK field is excluded from generated resumes and from
auto-submitted form answers until Parth confirms it. This script is the
gate — run it before any apply phase goes live.
"""
import sys, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def walk(node, path=""):
    if isinstance(node, dict):
        if node.get("status") == "ASK":
            yield path
            return
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            label = v.get("id") if isinstance(v, dict) and "id" in v else i
            yield from walk(v, f"{path}[{label}]")


def main():
    gaps = []
    for name in ("master.yaml", "answers.yaml"):
        doc = yaml.safe_load((ROOT / "profile" / name).read_text())
        gaps += [f"{name}: {p}" for p in walk(doc)]

    inferred = yaml.safe_load((ROOT / "profile" / "master.yaml").read_text())["skills"]
    n_inferred = sum(len(v.get("inferred", [])) for v in inferred.values())

    print(f"\n{len(gaps)} unverified field(s) — excluded from output until confirmed:\n")
    for g in gaps:
        print(f"  ASK  {g}")
    print(f"\n{n_inferred} inferred skill(s) held back pending confirmation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
