from alfabetizacao_pipeline.streaming.workflow_state import (
    JobState,
    PollPolicy,
    evaluate_poll,
)


def test_running_to_drained_is_success() -> None:
    # Given a job that reaches the required terminal state before its deadline
    states = (JobState.RUNNING, JobState.DRAINING, JobState.DRAINED)

    # When the state machine evaluates polling
    result = evaluate_poll(states, PollPolicy(target=JobState.DRAINED, max_polls=3))

    # Then it reports successful drain without cancellation
    assert result.success is True
    assert result.cancel_required is False
    assert result.final_state is JobState.DRAINED


def test_running_timeout_requires_cancel_and_is_failure() -> None:
    # Given a job that remains running through its deadline
    states = (JobState.RUNNING, JobState.RUNNING, JobState.CANCELLED)

    # When the state machine reaches the polling limit
    result = evaluate_poll(states, PollPolicy(target=JobState.DRAINED, max_polls=2))

    # Then cancellation is a fallback and never a successful outcome
    assert result.success is False
    assert result.cancel_required is True
    assert result.final_state is JobState.RUNNING


def test_cancelled_and_failed_states_are_terminal_failures() -> None:
    # Given cloud terminal states that must never be treated as drained
    policy = PollPolicy(target=JobState.DRAINED, max_polls=4)

    # When each state is evaluated
    cancelled = evaluate_poll((JobState.RUNNING, JobState.CANCELLED), policy)
    failed = evaluate_poll((JobState.PENDING, JobState.FAILED), policy)

    # Then both fail without requesting a second cancellation
    assert cancelled.success is False
    assert cancelled.cancel_required is False
    assert failed.success is False
    assert failed.cancel_required is False


def test_empty_observation_times_out_from_pending() -> None:
    # Given no state returned by the provider
    policy = PollPolicy(target=JobState.RUNNING, max_polls=1)

    # When the policy is evaluated
    result = evaluate_poll((), policy)

    # Then orchestration fails closed and requests cleanup
    assert result.success is False
    assert result.cancel_required is True
    assert result.final_state is JobState.PENDING
