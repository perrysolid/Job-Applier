#!/usr/bin/env python
"""Produce profile/master.example.yaml — the structure, none of the PII.

The real master.yaml is gitignored. This keeps the repo publishable while
still documenting the schema anyone (including future-you) needs to fill in.
"""
import pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
REDACT_KEYS = {
    "full_name", "first_name", "last_name", "email", "phone", "phone_national",
    "linkedin", "github", "github_secondary", "line1", "pincode", "owner",
    "date_of_birth", "gender", "category", "differently_abled",
}


def scrub(node, key=None):
    if isinstance(node, dict):
        return {k: scrub(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [scrub(v) for v in node]
    if key in REDACT_KEYS and node is not None:
        return f"<your {key.replace('_', ' ')}>"
    return node


def main():
    for name in ("master.yaml", "answers.yaml"):
        src = ROOT / "profile" / name
        if not src.exists():
            continue
        doc = scrub(yaml.safe_load(src.read_text()))
        out = ROOT / "profile" / name.replace(".yaml", ".example.yaml")
        out.write_text(
            "# Redacted template. Copy to "
            f"{name}, fill in your own details, and keep it out of git.\n"
            + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
        )
        print(f"wrote profile/{out.name}")


if __name__ == "__main__":
    main()
