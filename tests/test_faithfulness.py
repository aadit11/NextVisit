"""Reject a work order that invents a code or drops the official sentence."""

from nextvisit.workorder.faithfulness import WorkOrderItem, faithfulness_errors

CODEBOOK = {"02G": "Cold food item held above 41 F except during necessary preparation."}


def test_accepts_a_step_that_keeps_the_span_and_cuisine() -> None:
    item = WorkOrderItem(
        station="cold_holding",
        violation_code="02G",
        source_span="Cold food item held above 41 F",
        step="Japanese: at close, check the display case. Cold food item held above 41 F.",
    )
    errors = faithfulness_errors(
        predicted_codes=["02G"],
        codebook=CODEBOOK,
        cuisine="Japanese",
        items=[item],
        require_cuisine=True,
    )
    assert errors == []


def test_rejects_an_unknown_code_and_a_missing_span() -> None:
    item = WorkOrderItem(
        station="cold_holding",
        violation_code="99Z",
        source_span="invented wording",
        step="Japanese: invented wording",
    )
    errors = faithfulness_errors(
        predicted_codes=["02G"],
        codebook=CODEBOOK,
        cuisine="Japanese",
        items=[item],
        require_cuisine=True,
    )
    assert errors
