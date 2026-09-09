"""Emit the canonical Python runtime files for a Vercel preview API request.

Development dependencies, legacy handlers, tests and local data exports are excluded.
Usage: python scripts/deployment_files.py > /tmp/tei-deployment-files.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "app.py", "pyproject.toml", "requirements.txt", "src/__init__.py",
    "src/cloud_company.py", "src/public_config.py", "src/sources/judicial_index.py",
    "src/sources/procurement.py", "data/judicial_company_index.json",
    "web/index.html", "web/app.js", "web/tei-enhancements.js",
    "src/entities/__init__.py", "src/entities/models.py", "src/entities/repository.py",
    "src/entities/api.py", "src/relationships/__init__.py", "src/relationships/models.py",
]

if __name__ == "__main__":
    print(json.dumps([{"file": name, "data": (ROOT / name).read_text(), "encoding": "utf-8"}
                      for name in FILES], ensure_ascii=False))
