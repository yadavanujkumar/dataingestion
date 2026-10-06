from __future__ import annotations

import pytest
from howlplatform.deliverables.contract import (
    Requirement,
    GeneratorSpec,
    Generator,
    list_generators,
    get_generator,
    register_generator,
)


def test_built_in_generators_registered():
    registered = list_generators()
    assert "gsc_organic_report" in registered
    assert "paid_social_report" in registered
    assert "engagement_rate_report" in registered


def test_generator_spec_properties():
    gen_cls = get_generator("gsc_organic_report")
    assert gen_cls is not None
    spec = gen_cls.spec
    assert spec.name == "gsc_organic_report"
    assert spec.version == "1.0.0"
    assert any(req.domain == "search" for req in spec.requires)


def test_custom_generator_registration():
    class DummyGenerator(Generator):
        spec = GeneratorSpec(
            name="test_dummy_report",
            version="0.1.0",
            requires=(Requirement("paid", "paid_v2", ("spend",)),),
            outputs=("xlsx",),
            blocking_checks=(),
        )

        def build(self, brand: dict, period: str, data: dict, out_dir: str):
            return ["out.xlsx"]

    register_generator(DummyGenerator)
    assert "test_dummy_report" in list_generators()
    assert get_generator("test_dummy_report") is DummyGenerator
