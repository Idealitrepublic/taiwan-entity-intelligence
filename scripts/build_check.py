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
    # Vercel selects pyproject.toml over requirements.txt; keep both in sync.
    runtime_dependencies = {line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines()
                            if line.strip() and not line.lstrip().startswith("#")}
    assert set(config["project"].get("dependencies", [])) == runtime_dependencies
    files = [ROOT / "app.py", *sorted((ROOT / "src").rglob("*.py"))]
    for file in files:
        ast.parse(file.read_text(), filename=str(file))
    from app import app
    statuses = []
    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/"},
                       lambda status, headers: statuses.append(status)))
    assert statuses == ["200 OK"] and b"Taiwan Entity Intelligence" in body
    assert (ROOT / "data/judicial_company_index.json").is_file()
    assert (ROOT / "data/judicial_verified_cases.json").is_file()
    # Verify the actual PDF runtime and deployed font, not just Python syntax.
    from src.report_pdf import render_report_pdf
    pdf = render_report_pdf({"title": "T.E.I. 中文 / PDF", "methodology": "Build check",
                             "report_type": "ENTITY", "generated_at": "build",
                             "coverage": {}})
    assert pdf.startswith(b"%PDF-")
    print(f"Python bundle check passed: {len(files)} modules, WSGI entrypoint and required assets.")


if __name__ == "__main__":
    main()
