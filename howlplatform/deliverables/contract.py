"""
Generator Contract and Registry.
Matches HOWL Document 04 Section 5.
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Type


@dataclass(frozen=True)
class Requirement:
    """Declares a data dependency required by a generator."""
    domain: str                # e.g. "search", "paid", "organic"
    min_version: str           # e.g. "search_v1", "paid_v2"
    columns: Tuple[str, ...]   # e.g. ("impressions", "clicks", "ctr")


@dataclass(frozen=True)
class GeneratorSpec:
    """Specification describing a deliverable generator."""
    name: str                          # e.g. "gsc_organic_report"
    version: str                       # e.g. "1.0.0"
    requires: Tuple[Requirement, ...]  # Input data requirements
    outputs: Tuple[str, ...]           # e.g. ("xlsx",), ("pptx",)
    blocking_checks: Tuple[str, ...]   # Data quality checks that pause run on failure
    uses_narrative: bool = False       # Whether generator calls Claude for narrative draft


class Generator(ABC):
    """
    Abstract base class for all deliverable report generators.
    Rules:
      1. A generator never reads raw source files directly.
      2. A generator never writes directly to canonical database tables.
      3. A generator produces deterministic output given the same inputs and version.
    """
    spec: GeneratorSpec

    @abstractmethod
    def build(self, brand: dict, period: str, data: dict, out_dir: str) -> List[str]:
        """
        Build the deliverable output file(s).
        :param brand: The validated brand manifest dictionary.
        :param period: The reporting period (e.g. "2026-08").
        :param data: Dictionary of domain -> list/dataframe of canonical rows.
        :param out_dir: Output directory path where files must be saved.
        :return: List of created file paths.
        """
        pass

    def check_requirements(self, available_data: Dict[str, Any]) -> List[str]:
        """Verify that all required domains and columns exist and have non-empty data."""
        missing = []
        for req in self.spec.requires:
            if req.domain not in available_data:
                missing.append(f"Missing required domain: {req.domain}")
                continue
            rows = available_data[req.domain]
            if not rows:
                missing.append(f"Domain {req.domain} has no data rows for period")
        return missing


# Global registry for generators
_REGISTRY: Dict[str, Type[Generator]] = {}


def register_generator(cls: Type[Generator]) -> Type[Generator]:
    """Register a generator class in the platform registry."""
    if not hasattr(cls, "spec") or not isinstance(cls.spec, GeneratorSpec):
        raise TypeError(f"Class {cls.__name__} must define a 'spec' attribute of type GeneratorSpec.")
    _REGISTRY[cls.spec.name] = cls
    return cls


def get_generator(name: str) -> Optional[Type[Generator]]:
    """Retrieve a generator class by deliverable name, auto-loading if needed."""
    if name not in _REGISTRY:
        # Try dynamic import from known package
        try:
            importlib.import_module(f"howlplatform.deliverables.{name}.generator")
        except (ModuleNotFoundError, ImportError):
            pass
    return _REGISTRY.get(name)


def list_generators() -> List[str]:
    """List all registered deliverable generator names."""
    # Ensure known generators are loaded
    for gen_name in ["gsc_organic_report", "paid_social_report", "engagement_rate_report"]:
        if gen_name not in _REGISTRY:
            try:
                importlib.import_module(f"howlplatform.deliverables.{gen_name}.generator")
            except (ModuleNotFoundError, ImportError):
                pass
    return sorted(list(_REGISTRY.keys()))
