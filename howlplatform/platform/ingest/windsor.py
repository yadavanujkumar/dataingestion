from __future__ import annotations

import datetime
import json
import os
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from sqlalchemy.engine import Engine

from ..store.db import get_engine
from .drive import compute_file_sha256, is_file_already_ingested, record_raw_file

# Platform revision lookback windows in days (Document 04 Section 2)
REPULL_WINDOWS: Dict[str, int] = {
    "meta_ads": 28,
    "google_ads": 14,
    "linkedin_ads": 14,
    "google_search_console": 3,
    "ga4": 3,
    "default": 7,
}


def compute_fetch_date_range(channel: str, target_period: str) -> tuple[str, str]:
    """
    Computes start and end dates for a reporting period YYYY-MM,
    expanding start date backward by the channel's revision lookback window.
    """
    year, month = map(int, target_period.split("-"))
    # Period start date
    p_start = datetime.date(year, month, 1)

    # Period end date
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    p_end = next_month - datetime.timedelta(days=1)

    lookback_days = REPULL_WINDOWS.get(channel, REPULL_WINDOWS["default"])
    fetch_start = p_start - datetime.timedelta(days=lookback_days)

    return fetch_start.isoformat(), p_end.isoformat()


class WindsorPuller:
    """Client for Windsor.ai REST API with automated window re-pull and caching."""

    def __init__(self, api_key: Optional[str] = None, engine: Optional[Engine] = None):
        self.api_key = api_key or os.environ.get("WINDSOR_API_KEY")
        self.engine = engine or get_engine()
        self.base_url = "https://connectors.windsor.ai"

    def pull_source_data(
        self,
        source_config: Dict[str, Any],
        period: str,
        run_id: str,
        fixture_fallback: Optional[Path | str] = None,
    ) -> Path:
        """
        Pull connector data for the source and period.
        If WINDSOR_API_KEY is missing, falls back cleanly to fixture_fallback if provided.
        Saves raw data and returns saved raw file Path.
        """
        source_id = source_config["source_id"]
        channel = source_config["channel"]
        start_date, end_date = compute_fetch_date_range(channel, period)

        raw_dir = Path.cwd() / "raw_data" / source_config.get("brand_id", "default") / channel
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file_path = raw_dir / f"{source_id}_{period}_{start_date}_to_{end_date}.json"

        if self.api_key:
            # Query Windsor.ai REST API
            endpoint = f"{self.base_url}/{channel}"
            params = {
                "api_key": self.api_key,
                "date_from": start_date,
                "date_to": end_date,
                "accounts": source_config.get("account_ref", ""),
            }
            resp = requests.get(endpoint, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            with open(raw_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        elif fixture_fallback and Path(fixture_fallback).is_file():
            # Use local fixture as simulated raw payload
            p_fix = Path(fixture_fallback)
            with open(p_fix, "r", encoding="utf-8") as f:
                content = f.read()
            raw_file_path = raw_dir / f"{source_id}_{period}_{p_fix.name}"
            with open(raw_file_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            # Generate empty or mock response
            with open(raw_file_path, "w", encoding="utf-8") as f:
                json.dump({"data": [], "simulated": True}, f)

        # Register in raw_files table
        record_raw_file(
            source_id=source_id,
            run_id=run_id,
            file_path=raw_file_path,
            engine=self.engine,
        )

        return raw_file_path
