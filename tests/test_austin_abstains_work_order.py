"""Austin publishes scores only, so the work order stays empty."""

from nextvisit.workorder.generate import build_work_order


def test_austin_returns_no_work_order() -> None:
    order = build_work_order(
        "austin",
        cuisine=None,
        predicted_codes=["score"],
        codebook={},
    )
    assert order == []
