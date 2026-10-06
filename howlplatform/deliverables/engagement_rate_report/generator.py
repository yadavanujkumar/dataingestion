from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
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
        paid_rows = data.get("paid", [])
        organic_rows = data.get("organic", [])

        if not paid_rows and not organic_rows:
            raise ValueError(f"No paid or organic data provided for engagement rate report ({period}).")

        # Visual styling
        identity = brand.get("identity", {})
        display_name = identity.get("display_name", "Brand")
        palette = identity.get("palette", ["1C2321", "4E8C2B"])
        primary_hex = palette[0].replace("#", "")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        header_fill = PatternFill(start_color=primary_hex, end_color=primary_hex, fill_type="solid")
        light_gray_fill = PatternFill(start_color="F4F6F5", end_color="F4F6F5", fill_type="solid")

        font_header = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        font_title = Font(name="Arial", size=14, bold=True, color="1C2321")
        font_subtitle = Font(name="Arial", size=10, italic=True, color="555555")
        font_bold = Font(name="Arial", size=10, bold=True)
        font_regular = Font(name="Arial", size=10)

        thin_side = Side(border_style="thin", color="CCCCCC")
        thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")
        align_center = Alignment(horizontal="center", vertical="center")

        # Platforms tracked
        platforms = ["Instagram", "Facebook", "YouTube", "LinkedIn"]

        # Aggregate counts by platform for Paid and Organic
        paid_counts = {p.lower(): {"engagements": 0, "impressions": 0} for p in platforms}
        organic_counts = {p.lower(): {"engagements": 0, "impressions": 0} for p in platforms}

        for r in paid_rows:
            # Match channel / platform name
            chan = getattr(r, "channel", "").lower()
            camp = getattr(r, "campaign", "").lower()
            matched_p = None
            for p in platforms:
                if p.lower() in chan or p.lower() in camp:
                    matched_p = p.lower()
                    break
            if not matched_p:
                matched_p = "instagram"  # Default paid social channel if Meta Ads

            paid_counts[matched_p]["engagements"] += (getattr(r, "engagements", 0) or 0)
            paid_counts[matched_p]["impressions"] += (getattr(r, "impressions", 0) or 0)

        for r in organic_rows:
            chan = getattr(r, "channel", "").lower()
            matched_p = None
            for p in platforms:
                if p.lower() in chan:
                    matched_p = p.lower()
                    break
            if matched_p:
                eng = getattr(r, "engagements", 0) or 0
                # YouTube denominator: views if present, else impressions (Document 06)
                if matched_p == "youtube":
                    imp = getattr(r, "video_views", None) or getattr(r, "impressions", 0) or 0
                else:
                    imp = getattr(r, "impressions", 0) or 0
                organic_counts[matched_p]["engagements"] += eng
                organic_counts[matched_p]["impressions"] += imp

        # ==============================================================
        # TAB 1: Engagement Rates
        # ==============================================================
        ws = wb.create_sheet(title="Engagement Rates")
        ws.views.sheetView[0].showGridLines = True

        ws["A1"] = f"{display_name} - Multi-Channel Engagement Rate Report"
        ws["A1"].font = font_title
        ws["A2"] = f"Reporting Period: {period} | Method: Ratio-of-Sums (sum of engagements / sum of impressions)"
        ws["A2"].font = font_subtitle

        def render_table(start_row: int, title: str, counts_dict: Optional[Dict[str, Dict[str, int]]] = None, is_total: bool = False):
            ws.cell(row=start_row, column=1, value=title).font = font_bold
            headers = ["Platform", "Total Impressions", "Total Engagements", "Engagement Rate"]
            for col_idx, h in enumerate(headers, start=1):
                cell = ws.cell(row=start_row + 1, column=col_idx, value=h)
                cell.fill = header_fill
                cell.font = font_header
                cell.alignment = align_center

            for offset, p_name in enumerate(platforms, start=start_row + 2):
                p_key = p_name.lower()
                if is_total:
                    imps = paid_counts[p_key]["impressions"] + organic_counts[p_key]["impressions"]
                    engs = paid_counts[p_key]["engagements"] + organic_counts[p_key]["engagements"]
                else:
                    imps = counts_dict[p_key]["impressions"]
                    engs = counts_dict[p_key]["engagements"]

                if imps > 0:
                    rate = engs / imps
                    rate_str = f"{rate * 100:.2f}%"
                else:
                    rate_str = "-"

                row_vals = [
                    p_name,
                    f"{imps:,}" if imps > 0 else "-",
                    f"{engs:,}" if engs > 0 else "-",
                    rate_str
                ]
                for c_idx, val in enumerate(row_vals, start=1):
                    c = ws.cell(row=offset, column=c_idx, value=val)
                    c.font = font_regular
                    c.alignment = align_left if c_idx == 1 else align_right
                    c.border = thin_border

        # 1. Paid Table (Row 4-9)
        render_table(4, "Table 1: Paid Media Engagement Rates", counts_dict=paid_counts)

        # 2. Organic Table (Row 11-16)
        render_table(11, "Table 2: Organic Social Engagement Rates", counts_dict=organic_counts)

        # 3. Total Combined Table (Row 18-23)
        render_table(18, "Table 3: Total Combined Engagement Rates (Ratio-of-Sums)", is_total=True)

        # ==============================================================
        # TAB 2: Notes & Methodology
        # ==============================================================
        ws_notes = wb.create_sheet(title="Methodology")
        ws_notes.views.sheetView[0].showGridLines = True

        ws_notes["A1"] = "HOWL Engagement Rate Methodology & Correction Log"
        ws_notes["A1"].font = font_title

        doc6_notes = [
            ("Core Principle", "Ingest counts, never rates. All averages are computed as ratio of sums."),
            ("Why not average percentages?", "Averaging monthly percentages weights a 500-impression month equally with a 5,000,000-impression month."),
            ("Combined Total Rule", "Total engagement rate must strictly fall between Paid and Organic rates."),
            ("YouTube Denominator", "Views (rather than raw impressions) used for YouTube video engagements."),
            ("Missing Data Format", "Hyphen '-' denotes no activity, never 0.00%."),
        ]
        ws_notes.cell(row=3, column=1, value="Methodology Rule").font = font_header
        ws_notes.cell(row=3, column=1).fill = header_fill
        ws_notes.cell(row=3, column=2, value="Rationale & Specification").font = font_header
        ws_notes.cell(row=3, column=2).fill = header_fill

        for idx, (k, v) in enumerate(doc6_notes, start=4):
            c1 = ws_notes.cell(row=idx, column=1, value=k)
            c1.font = font_bold
            c1.border = thin_border
            c2 = ws_notes.cell(row=idx, column=2, value=v)
            c2.font = font_regular
            c2.border = thin_border

        for sheet in wb.worksheets:
            for col in sheet.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                sheet.column_dimensions[col_letter].width = max(max_len + 3, 14)

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        final_file = out_path / f"{display_name.lower()}_engagement_rate_{period}.xlsx"
        wb.save(final_file)
        return [str(final_file.resolve())]
