#!/usr/bin/env python
"""Temporary: list Gemini models available for your API key (supports generateContent)."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
env_file = BASE / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v

api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Set GOOGLE_API_KEY or GEMINI_API_KEY (or in .env)", file=sys.stderr)
    sys.exit(1)

try:
    from google.genai import Client
except ImportError:
    print("Install: pip install google-genai", file=sys.stderr)
    sys.exit(1)

client = Client(api_key=api_key)
print("Models that support generateContent:\n")
for m in client.models.list():
    name = getattr(m, "name", None) or str(m)
    if "models/" in name:
        name = name.replace("models/", "")
    methods = getattr(m, "supported_generation_methods", None) or []
    if not methods or "generateContent" in methods:
        print(name)
client.close()
print("\n(Done)")
