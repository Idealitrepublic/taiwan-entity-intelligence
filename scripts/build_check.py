"""Validate the actual Python deployment bundle, without claiming a Next.js build."""
import ast
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["tool"]["vercel"]["entrypoint"] == "app:app"
    files = [ROOT / "app.py", *sorted((ROOT / "src").rglob("*.py"))]
    for file in files:
        ast.parse(file.read_text(), filename=str(file))
    from app import app
    statuses = []
    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"},
                       lambda status, headers: statuses.append(status)))
    assert statuses == ["200 OK"] and b"Taiwan Entity Intelligence" in body
    assert (ROOT / "data/judicial_company_index.json").is_file()
    print(f"Python bundle check passed: {len(files)} modules, WSGI entrypoint and required assets.")


if __name__ == "__main__":
    main()
