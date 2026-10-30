#!/usr/bin/env python3
"""Create .env from .env.example and generate secrets. Safe to re-run (never overwrites existing values)."""
import re
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
env, example = root / ".env", root / ".env.example"
if not env.exists():
    env.write_text(example.read_text())
    print("Created .env from .env.example")
text = env.read_text()


def fill(key: str, value: str) -> None:
    global text
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    if m and not m.group(1).strip():
        text = text.replace(m.group(0), f"{key}={value}", 1)
        print(f"Generated {key}")


fill("SECRET_KEY", secrets.token_hex(32))
fill("POSTGRES_PASSWORD", secrets.token_hex(16))

m = re.search(r"^GEMINI_API_KEY=(.*)$", text, re.M)
if m and not m.group(1).strip() and sys.stdin.isatty():
    key = input("Paste your Gemini API key (or press Enter to add it later): ").strip()
    if key:
        text = text.replace(m.group(0), f"GEMINI_API_KEY={key}", 1)

env.write_text(text)

if not re.search(r"^GEMINI_API_KEY=\S+", text, re.M):
    print("\n!  GEMINI_API_KEY is empty. Edit .env and add it – get a free key at https://aistudio.google.com/app/apikey")
print("Done. .env is git-ignored – keep it private.")
