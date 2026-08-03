import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledgebase.admin_dashboard_stats import build_combined_summary

OUTPUT_PATH = Path(__file__).resolve().parent / "combined_dashboard_summary.json"


if __name__ == "__main__":
    summary = build_combined_summary(output_path=OUTPUT_PATH)
    print(f"Wrote {OUTPUT_PATH}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
