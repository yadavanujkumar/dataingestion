from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine

from howlplatform.platform.classifier.classifier import QueryClassifier
from howlplatform.platform.ledger.ledger import record_decision
from howlplatform.platform.manifest.loader import load_manifest
from howlplatform.platform.store.db import run_migrations

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def classifier_fixture():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    manifest = load_manifest(REPO_ROOT / "manifests" / "ampere.json")
    classifier = QueryClassifier(manifest, engine=engine)
    return classifier, engine


def test_classify_canonical_brand(classifier_fixture):
    classifier, _ = classifier_fixture
    res = classifier.classify_query("ampere electric scooter", 100, 1000)
    assert res["is_branded"] is True
    assert res["brand_form"] == "canonical"
    assert res["tag_source"] == "rule"


def test_classify_misspelling(classifier_fixture):
    classifier, _ = classifier_fixture
    res = classifier.classify_query("ampaire scooter price", 50, 500)
    assert res["is_branded"] is True
    assert res["brand_form"] == "misspelling"
    assert res["tag_source"] == "rule"


def test_classify_product_match(classifier_fixture):
    classifier, _ = classifier_fixture
    res = classifier.classify_query("magnus g max battery", 80, 800)
    assert res["product"] == "Magnus G Max"


def test_classify_sensitive_real_word(classifier_fixture):
    classifier, _ = classifier_fixture
    # Unrelated real word "amber" without context should NOT match brand
    res_unrelated = classifier.classify_query("amber color stone necklace", 10, 100)
    assert res_unrelated["is_branded"] is False

    # "amber" with category context "scooter" SHOULD match brand
    res_context = classifier.classify_query("amber scooter price", 10, 100)
    assert res_context["is_branded"] is True
    assert res_context["brand_form"] == "misspelling"


def test_classify_ledger_override(classifier_fixture):
    classifier, engine = classifier_fixture
    # Before ledger
    res1 = classifier.classify_query("electric two wheeler showroom near me", 25, 3000)
    assert res1["tag_source"] == "unclassified"

    # Record decision in ledger
    record_decision(
        brand_id="ampere",
        entity_type="query",
        entity_key="electric two wheeler showroom near me",
        decision="reclassify",
        value={"is_branded": False, "product": None, "generic_theme": "dealership"},
        decided_by="analyst@howl.internal",
        engine=engine,
    )

    # After ledger
    res2 = classifier.classify_query("electric two wheeler showroom near me", 25, 3000)
    assert res2["tag_source"] == "ledger"
    assert res2["generic_theme"] == "dealership"
