from __future__ import annotations

from typing import Any, Dict, List, Optional


def compute_entity_impact(domain: str, metrics: Dict[str, Any]) -> float:
    """
    Computes business impact score per domain matching HOWL Document 02 Section 6:
      - search: clicks (fallback to 0.01 * impressions)
      - paid: spend in account currency
      - organic: impressions
      - web: sessions
      - crm: deal/pipeline value
    """
    domain = domain.lower()
    if domain == "search":
        clicks = float(metrics.get("clicks", 0))
        if clicks > 0:
            return clicks
        return float(metrics.get("impressions", 0)) * 0.01

    elif domain == "paid":
        return float(metrics.get("spend", 0.0))

    elif domain == "organic":
        return float(metrics.get("impressions", 0))

    elif domain == "web":
        return float(metrics.get("sessions", 0))

    elif domain == "crm":
        return float(metrics.get("value", 0.0))

    # Default fallback: clicks or impressions
    return float(metrics.get("clicks", metrics.get("impressions", 1.0)))


def rank_items_by_impact(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort review items in descending order of impact."""
    return sorted(items, key=lambda x: float(x.get("impact", 0.0)), reverse=True)
