from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..store.db import get_engine
from ..review.queue import create_review_item


def parse_percentage_cell(val: Any) -> Optional[float]:
    """Convert '16.45%' to 0.1645, '-' or empty to None."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "-", "N/A", "n/a"):
        return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        f = float(s)
        return round(f / 100.0, 6)
    except ValueError:
        return None


class LegacySheetImporter:
    """Imports historical report tables flagged as legacy (Document 06 Section 5)."""

    def __init__(self, brand_id: str = "ampere", engine: Optional[Engine] = None):
        self.brand_id = brand_id
        self.engine = engine or get_engine()

    def import_legacy_sheet(self, file_path: Path | str, run_id: str = "legacy_import") -> List[Dict[str, Any]]:
        """
        Parses legacy engagement rate CSV and flags problem cells
        (e.g. rate > 1.0 or massive outliers) straight to the review queue.
        """
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Legacy file not found: {p}")

        rows = []
        with open(p, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            month_cols = [c for c in (reader.fieldnames or []) if c.lower() not in ("platform", "type")]

            for raw in reader:
                platform = raw.get("platform", "").strip()
                p_type = raw.get("type", "").strip()

                for m_col in month_cols:
                    raw_val = raw.get(m_col)
                    rate = parse_percentage_cell(raw_val)

                    if rate is not None and rate > 1.0:
                        # Problem cell: over 100% (Document 06 Section 2.3)
                        create_review_item(
                            brand_id=self.brand_id,
                            run_id=run_id,
                            entity_type="record",
                            entity_key=f"legacy:{platform}:{p_type}:{m_col}",
                            impact=100.0,
                            reason=f"Legacy engagement rate exceeds 100% ({rate*100:.2f}%)",
                            engine=self.engine,
                        )

                    rows.append({
                        "brand_id": self.brand_id,
                        "platform": platform.lower(),
                        "type": p_type.lower(),
                        "period": m_col,
                        "metric": "engagement_rate",
                        "value": rate,
                        "source_id": f"{self.brand_id}-legacy",
                    })

        return rows
