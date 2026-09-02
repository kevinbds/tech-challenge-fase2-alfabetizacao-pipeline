from alfabetizacao_pipeline.streaming.workflow_state import (
    JobState,
    PollPolicy,
    evaluate_poll,
)


def test_running_to_drained_is_success() -> None:
    states = (JobState.RUNNING, JobState.DRAINING, JobState.DRAINED)

    result = evaluate_poll(states, PollPolicy(target=JobState.DRAINED, max_polls=3))

    assert result.success is True
    assert result.cancel_required is False
    assert result.final_state is JobState.DRAINED


def test_running_timeout_requires_cancel_and_is_failure() -> None:
    states = (JobState.RUNNING, JobState.RUNNING, JobState.CANCELLED)

    result = evaluate_poll(states, PollPolicy(target=JobState.DRAINED, max_polls=2))

    assert result.success is False
    assert result.cancel_required is True
    assert result.final_state is JobState.RUNNING


def test_cancelled_and_failed_states_are_terminal_failures() -> None:
    policy = PollPolicy(target=JobState.DRAINED, max_polls=4)

    cancelled = evaluate_poll((JobState.RUNNING, JobState.CANCELLED), policy)
    failed = evaluate_poll((JobState.PENDING, JobState.FAILED), policy)

    assert cancelled.success is False
    assert cancelled.cancel_required is False
    assert failed.success is False
    assert failed.cancel_required is False


def test_empty_observation_times_out_from_pending() -> None:
    policy = PollPolicy(target=JobState.RUNNING, max_polls=1)

    result = evaluate_poll((), policy)

    assert result.success is False
    assert result.cancel_required is True
    assert result.final_state is JobState.PENDING
