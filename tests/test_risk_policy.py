from services.risk_policy import should_block_by_risk


def test_should_block_by_risk_blocks_block_decision_regardless_of_restrict_policy():
    assert should_block_by_risk("block", block_on_restrict=False) is True
    assert should_block_by_risk("block", block_on_restrict=True) is True


def test_should_block_by_risk_respects_restrict_policy():
    assert should_block_by_risk("restrict", block_on_restrict=False) is False
    assert should_block_by_risk("restrict", block_on_restrict=True) is True


def test_should_block_by_risk_does_not_block_allow_or_unknown_values():
    assert should_block_by_risk("allow", block_on_restrict=True) is False
    assert should_block_by_risk("unknown", block_on_restrict=True) is False
    assert should_block_by_risk("", block_on_restrict=True) is False
