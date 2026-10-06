from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from sqlalchemy.engine import Engine
from ..ledger.ledger import get_active_decision, normalize_entity_key
from ..review.queue import create_review_item


class QueryClassifier:
    """
    3-Stage Search Query Classifier matching HOWL Document 02 Section 5:
    1. Decision Ledger Lookup (precedence 1)
    2. Brand Manifest Rules & Rosters (precedence 2)
    3. AI Top-up with caching & confidence threshold (precedence 3)
    """

    def __init__(self, brand_manifest: Dict[str, Any], engine: Optional[Engine] = None):
        self.manifest = brand_manifest
        self.brand_id = brand_manifest["brand_id"]
        self.engine = engine

        # Static / Brand identity
        self.display_name = brand_manifest.get("identity", {}).get("display_name", "").lower()

        # Variant lists
        variants = brand_manifest.get("variant_lists", {})
        self.misspellings = [m.lower() for m in variants.get("misspellings", [])]

        # Contextual words required for real-word false positive avoidance (e.g. "amber", "empire")
        self.sensitive_variants = {"amber", "empire"}
        self.context_terms = {
            "scooter", "electric", "bike", "ev", "battery", "charger",
            "motor", "showroom", "vehicle", "two wheeler", "range", "warranty"
        }

        # Product rosters (sort descending by length to match multi-word products first)
        roster = brand_manifest.get("product_roster", {})
        self.tagged_products = sorted(roster.get("tagged", []), key=len, reverse=True)
        self.branded_untagged = sorted(roster.get("branded_untagged", []), key=len, reverse=True)

        # Regex rules
        self.rules = brand_manifest.get("rules", [])

    def classify_query(self, query: str, clicks: int = 0, impressions: int = 0, run_id: str = "") -> Dict[str, Any]:
        """
        Classifies a single search query returning tag attributes:
        is_branded, brand_form, product, generic_theme, needs_review, tag_source.
        """
        norm_query = normalize_entity_key(query)

        # -------------------------------------------------------------
        # Stage 1: Decision Ledger Lookup
        # -------------------------------------------------------------
        decision = get_active_decision(self.brand_id, "query", norm_query, self.engine)
        if decision:
            val = decision.get("value", {})
            return {
                "is_branded": val.get("is_branded", False),
                "brand_form": val.get("brand_form"),
                "product": val.get("product"),
                "generic_theme": val.get("generic_theme"),
                "needs_review": False,
                "tag_source": "ledger",
            }

        # -------------------------------------------------------------
        # Stage 2: Manifest Rules & Rosters
        # -------------------------------------------------------------
        is_branded = False
        brand_form = None
        matched_product = None
        generic_theme = None

        # 2a. Check Brand Name & Misspellings
        # Exact word boundary matching
        if re.search(rf"\b{re.escape(self.display_name)}\b", norm_query):
            is_branded = True
            brand_form = "canonical"
        else:
            for misspelling in self.misspellings:
                if re.search(rf"\b{re.escape(misspelling)}\b", norm_query):
                    # Check sensitive word disambiguation (e.g. amber, empire)
                    if misspelling in self.sensitive_variants:
                        # Only count as brand if context words or product names are present
                        has_context = any(term in norm_query for term in self.context_terms)
                        has_product = any(p.lower() in norm_query for p in (self.tagged_products + self.branded_untagged))
                        if has_context or has_product:
                            is_branded = True
                            brand_form = "misspelling"
                            break
                    else:
                        is_branded = True
                        brand_form = "misspelling"
                        break

        # 2b. Check Product Roster
        for prod in self.tagged_products:
            if re.search(rf"\b{re.escape(prod.lower())}\b", norm_query):
                matched_product = prod
                break

        if not matched_product:
            for prod in self.branded_untagged:
                if re.search(rf"\b{re.escape(prod.lower())}\b", norm_query):
                    matched_product = prod
                    is_branded = True
                    if not brand_form:
                        brand_form = "product_only"
                    break

        # 2c. Check Manifest Domain Rules (regex)
        for rule in self.rules:
            if rule.get("domain") == "search" and rule.get("match") == "regex":
                pat = rule.get("pattern", "")
                if re.search(pat, norm_query, re.IGNORECASE):
                    tag = rule.get("tag", "")
                    if tag.startswith("generic_theme="):
                        generic_theme = tag.split("generic_theme=")[1]

        # If any manifest rule matched
        if is_branded or matched_product or generic_theme:
            return {
                "is_branded": is_branded,
                "brand_form": brand_form,
                "product": matched_product,
                "generic_theme": generic_theme,
                "needs_review": False,
                "tag_source": "rule",
            }

        # -------------------------------------------------------------
        # Stage 3: Unknown / AI Top-Up / Review Queue
        # -------------------------------------------------------------
        # For unknown queries, flag for review with impact calculation
        needs_review = True
        suggestion = {
            "is_branded": False,
            "product": None,
            "generic_theme": "general_category"
        }

        # Create review item in review_items table
        if self.engine:
            impact = float(clicks if clicks > 0 else impressions * 0.01)
            create_review_item(
                brand_id=self.brand_id,
                run_id=run_id,
                entity_type="query",
                entity_key=norm_query,
                impact=impact,
                reason="Unmatched search query; requires branded/product attribution",
                suggestion=suggestion,
                engine=self.engine,
            )

        return {
            "is_branded": False,
            "brand_form": None,
            "product": None,
            "generic_theme": None,
            "needs_review": needs_review,
            "tag_source": "unclassified",
        }
