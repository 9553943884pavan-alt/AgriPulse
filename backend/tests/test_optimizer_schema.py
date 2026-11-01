"""Contract tests for optimizer-ready inputs and explicit uncertainty."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import OptimizerInputs, Scenario, SourcedValue, UncertaintyBand
from tests.test_optimizer import _inputs, _sv


def test_uncertainty_band_requires_ordered_bounds():
    band = UncertaintyBand(
        lower=10.0,
        expected=12.0,
        upper=15.0,
        unit="quintal/acre",
        basis="documented test interval",
        status="assumption",
    )
    assert band.expected == 12.0

    with pytest.raises(ValidationError, match="lower <= expected <= upper"):
        UncertaintyBand(
            lower=15.0,
            expected=12.0,
            upper=10.0,
            unit="quintal/acre",
            basis="invalid test interval",
            status="assumption",
        )


def test_scenario_probability_is_a_probability():
    with pytest.raises(ValidationError):
        Scenario(
            id="normal",
            label="Normal",
            season_rain_mm=_sv(500, "mm", "official_dataset"),
            probability=1.1,
            analogue_year=2020,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("scenario_weights", [0.2, 0.6], "must contain drought, normal, and excess"),
        ("scenario_weights", [0.2, 0.6, 0.3], "must sum to 1"),
        ("water_budgets", [], "must contain exactly drought, normal, and excess"),
    ],
)
def test_optimizer_inputs_reject_ambiguous_scenario_contract(field, value, message):
    payload = _inputs().model_dump()
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        OptimizerInputs.model_validate(payload)


def test_optimizer_inputs_reject_duplicate_crop_ids():
    payload = _inputs().model_dump()
    payload["candidates"].append(payload["candidates"][0])

    with pytest.raises(ValidationError, match="duplicate crop_id"):
        OptimizerInputs.model_validate(payload)
