from alfabetizacao_pipeline.errors import ExitCode


def test_exit_codes_when_exposed_to_automation() -> None:
    expected = [0, 2, 3, 4, 5]
    actual = [int(code) for code in ExitCode]
    assert actual == expected
