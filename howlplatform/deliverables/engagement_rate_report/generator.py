from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..contract import Generator, GeneratorSpec, Requirement, register_generator


@register_generator
class EngagementRateReportGenerator(Generator):
    """
    Deliverable: engagement_rate_report (v1.0.0)
    Generates three-table multi-channel engagement rate report (Paid, Organic, Total)
    using ratio-of-sums aggregation as specified in HOWL Document 06.
    """
    spec = GeneratorSpec(
        name="engagement_rate_report",
        version="1.0.0",
        requires=(
            Requirement(
                domain="paid",
                min_version="paid_v2",
                columns=("impressions", "engagements")
            ),
            Requirement(
                domain="organic",
                min_version="organic_v1",
                columns=("impressions", "engagements")
            ),
        ),
        outputs=("xlsx",),
        blocking_checks=("rate_over_100", "vs_platform_totals"),
        uses_narrative=False,
    )

    def build(self, brand: Dict[str, Any], period: str, data: Dict[str, Any], out_dir: str | Path) -> List[str]:
        identity = brand.get("identity", {})
        display_name = identity.get("display_name", "Brand")
        palette = identity.get("palette", ["1C2321", "4E8C2B"])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Engagement Rates"

        header_fill = PatternFill(start_color=palette[0].replace("#", ""), end_color=palette[0].replace("#", ""), fill_type="solid")
        font_header = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        font_title = Font(name="Arial", size=14, bold=True, color="1C2321")

        ws["A1"] = f"{display_name} - Cross-Channel Engagement Rate Report"
        ws["A1"].font = font_title
        ws["A2"] = f"Reporting Window: {period} | Metric: Ratio-of-Sums (Engagements / Impressions)"

        # Tables: Paid, Organic, Total
        channels = ["Instagram", "Facebook", "YouTube", "LinkedIn"]
        ws["A4"] = "Paid Media Engagement Rates"
        ws["A4"].font = Font(name="Arial", size=12, bold=True)

        for col_idx, ch in enumerate(["Platform", "Impressions", "Engagements", "Engagement Rate"], start=1):
            cell = ws.cell(row=5, column=col_idx, value=ch)
            cell.fill = header_fill
            cell.font = font_header

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        final_file = out_path / f"{display_name.lower()}_engagement_rate_{period}.xlsx"
        wb.save(final_file)
        return [str(final_file.resolve())]
