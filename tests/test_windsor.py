from __future__ import annotations

import datetime
from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.ingest.windsor import (
    compute_fetch_date_range,
    REPULL_WINDOWS,
    WindsorPuller,
)
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_META = REPO_ROOT / "tests" / "fixtures" / "meta_ads_ampere_2026_08.csv"


def test_repull_windows_dates():
    # Meta Ads has 28-day lookback
    start_meta, end_meta = compute_fetch_date_range("meta_ads", "2026-08")
    assert end_meta == "2026-08-31"
    # 2026-08-01 minus 28 days = 2026-07-04
    assert start_meta == "2026-07-04"

    # GSC has 3-day lookback
    start_gsc, end_gsc = compute_fetch_date_range("google_search_console", "2026-08")
    # 2026-08-01 minus 3 days = 2026-07-29
    assert start_gsc == "2026-07-29"


def test_windsor_puller_with_fixture_fallback():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    puller = WindsorPuller(api_key=None, engine=engine)
    saved_file = puller.pull_source_data(
        source_config={"source_id": "ampere-meta-ads", "channel": "meta_ads", "brand_id": "ampere"},
        period="2026-08",
        run_id="test_run_windsor",
        fixture_fallback=SAMPLE_META,
    )
    assert saved_file.is_file()
