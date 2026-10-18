from nextvisit.model.baseline import repeat_last_visit


def test_baseline_repeats_the_previous_outcome() -> None:
    assert repeat_last_visit(True) is True
    assert repeat_last_visit(False) is False
