from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..manifest.loader import load_manifest, validate_manifest
from ..store.db import get_engine
from ..store.sync import sync_brand_manifest


def find_promotable_patterns(
    brand_id: str,
    min_count: int = 2,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Analyzes active decisions in the decision ledger to identify patterns
    eligible for promotion into manifest rules or variant lists.
    """
    if engine is None:
        engine = get_engine()

    # Query active decisions
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT d.entity_key, d.decision, d.value
                FROM decision_ledger d
                WHERE d.brand_id = :brand_id
                  AND d.decision_id NOT IN (
                      SELECT COALESCE(supersedes, '') FROM decision_ledger WHERE brand_id = :brand_id AND supersedes IS NOT NULL
                  )
            """),
            {"brand_id": brand_id}
        ).fetchall()

    theme_keywords = collections.defaultdict(lambda: collections.Counter())
    new_misspellings = set()

    for r in rows:
        key = r[0]
        val = r[2]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = {}

        # 1. Check for misspelling promotions
        if val.get("is_branded") and val.get("brand_form") == "misspelling":
            # Extract potential brand token from key
            tokens = key.split()
            if tokens:
                new_misspellings.add(tokens[0])

        # 2. Check for recurring generic themes
        theme = val.get("generic_theme")
        if theme:
            words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", key.lower()) if w not in ("near", "the", "for", "and")]
            for w in words:
                theme_keywords[theme][w] += 1

    promotable_rules = []
    for theme, counter in theme_keywords.items():
        for word, count in counter.items():
            if count >= min_count:
                promotable_rules.append({
                    "domain": "search",
                    "match": "regex",
                    "pattern": rf"\b({re.escape(word)})\b",
                    "tag": f"generic_theme={theme}",
                    "occurrence_count": count,
                })

    return {
        "promotable_rules": promotable_rules,
        "promotable_misspellings": list(new_misspellings),
    }


def promote_decisions_to_manifest(
    brand_id: str,
    min_count: int = 2,
    manifest_dir: Optional[Path | str] = None,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    """
    Promotes recurring ledger decisions into the brand's manifest JSON file,
    increments manifest_version, validates schema, and syncs to database.
    """
    if engine is None:
        engine = get_engine()

    base_dir = Path(manifest_dir or Path.cwd() / "manifests")
    manifest_file = base_dir / f"{brand_id}.json"
    manifest = load_manifest(manifest_file)

    candidates = find_promotable_patterns(brand_id, min_count, engine)
    promoted_rules = []
    promoted_misspellings = []

    # 1. Promote new rules
    existing_patterns = {r.get("pattern") for r in manifest.get("rules", [])}
    if "rules" not in manifest:
        manifest["rules"] = []

    for rule_cand in candidates["promotable_rules"]:
        pat = rule_cand["pattern"]
        if pat not in existing_patterns:
            manifest["rules"].append({
                "domain": rule_cand["domain"],
                "match": rule_cand["match"],
                "pattern": pat,
                "tag": rule_cand["tag"],
            })
            existing_patterns.add(pat)
            promoted_rules.append(rule_cand)

    # 2. Promote new misspellings
    if "variant_lists" not in manifest:
        manifest["variant_lists"] = {}
    current_misspellings = set(manifest.get("variant_lists", {}).get("misspellings", []))

    for m in candidates["promotable_misspellings"]:
        if m not in current_misspellings:
            current_misspellings.add(m)
            promoted_misspellings.append(m)

    manifest["variant_lists"]["misspellings"] = sorted(list(current_misspellings))

    # If any changes were made, increment version and save
    if promoted_rules or promoted_misspellings:
        manifest["manifest_version"] += 1
        errors = validate_manifest(manifest)
        if errors:
            raise ValueError(f"Promoted manifest failed validation: {errors}")

        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        sync_brand_manifest(manifest, engine)

    return {
        "brand_id": brand_id,
        "new_version": manifest["manifest_version"],
        "promoted_rules": promoted_rules,
        "promoted_misspellings": promoted_misspellings,
    }
