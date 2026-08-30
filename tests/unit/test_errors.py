from alfabetizacao_pipeline.errors import ExitCode


def test_exit_codes_when_exposed_to_automation() -> None:
    # Given: the public exit-code contract.
    expected = [0, 2, 3, 4, 5]

    # When: automation reads every code in declaration order.
    actual = [int(code) for code in ExitCode]

    # Then: every operational outcome remains stable.
    assert actual == expected
