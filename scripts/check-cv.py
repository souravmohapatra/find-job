"""Check a real local CV without persisting or printing its contents or calling an AI provider."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.documents.parser import DocumentError, detect_type  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("path", type=Path)
args = parser.parse_args()
path = args.path.resolve()
if not path.is_file() or not 0 < path.stat().st_size <= 10 * 1024 * 1024:
    raise SystemExit("Use an existing non-empty document of at most 10 MiB.")
try:
    media_type = detect_type(path.read_bytes())
except DocumentError as error:
    raise SystemExit(str(error)) from None
try:
    result = subprocess.run(
        [
            str(root / "backend/.venv/bin/python"),
            "-m",
            "app.documents.parser",
            str(path),
            media_type,
        ],
        cwd=root / "backend",
        env={"LANG": "C.UTF-8"},
        capture_output=True,
        timeout=25,
        check=False,
    )
except subprocess.TimeoutExpired:
    raise SystemExit("Parser exceeded its time limit.") from None
try:
    parsed = json.loads(result.stdout)
except (ValueError, UnicodeDecodeError):
    raise SystemExit(
        "Parser failed within its resource limits; document contents were not logged."
    ) from None
if result.returncode:
    raise SystemExit(parsed.get("error", "Document could not be parsed."))
spans = parsed["spans"]
print(
    json.dumps(
        {
            "format": media_type,
            "text_segments": len(spans),
            "pages_with_text": len({span["page"] for span in spans if span["page"] is not None}),
            "extracted_characters": sum(len(span["text"]) for span in spans),
            "persisted_content": False,
            "ai_requests": 0,
        },
        indent=2,
    )
)
print("Text extraction succeeded. Semantic accuracy and reading order still require review.")
