from __future__ import annotations

import hashlib

import numpy as np
import pytest

from houearth.core import LightCurve
from houearth.provenance import lightcurve_array_hashes


@pytest.fixture(autouse=True)
def _unique_phase12_locked_resume_fixture_arrays(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give every synthetic locked target a unique array identity.

    The locked-resume tests deliberately reject a campaign-input hash shared by two
    targets. Their small fixture must therefore avoid accidental collisions in its
    synthetic flux offsets. This fixture is scoped only to that test module and does
    not alter production behavior.
    """
    module = request.module
    if not module.__name__.endswith("test_phase12_locked_resume"):
        return

    ordinal_by_query: dict[str, int] = {}

    def digest(label: str) -> str:
        return hashlib.sha256(label.encode()).hexdigest()

    def unique_lightcurve(query: str) -> LightCurve:
        ordinal = ordinal_by_query.setdefault(query, len(ordinal_by_query) + 1)
        time = np.linspace(0.0, 48.0, 1200)
        flux = np.ones_like(time) + ordinal * 1e-7
        flux_error = np.full_like(time, 0.0002)
        hashes = lightcurve_array_hashes(time, flux, flux_error)
        return LightCurve(
            time,
            flux,
            flux_error,
            target=query,
            metadata={
                "sectors": [1, 2],
                "products": 2,
                "campaign_input_array_hashes": hashes,
                "query_provenance_sha256": digest(query + "-query"),
                "product_provenance_sha256": digest(query + "-products"),
            },
        )

    monkeypatch.setattr(module, "_synthetic_lightcurve", unique_lightcurve)
