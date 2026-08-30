import subprocess
import sys

import pytest

ORCHESTRATOR_PROGRAM = """
import sys
from alfabetizacao_pipeline.streaming.workflow_orchestrator import (
    FailurePoint, InMemoryWorkflowPort, WorkflowExecutionError, run_guarded_workflow
)
failure = FailurePoint(sys.argv[1])
port = InMemoryWorkflowPort(failure=failure)
try:
    result = run_guarded_workflow(port)
except WorkflowExecutionError:
    result = None
assert port.final_state.is_terminal
assert port.cleanup_waited
if failure in {
    FailurePoint.LAUNCH_AFTER_CREATE,
    FailurePoint.PRODUCER,
    FailurePoint.STAGE,
    FailurePoint.RAW_STALE,
}:
    assert port.cancel_requested
else:
    assert port.drain_requested
if failure is FailurePoint.NONE:
    assert result is not None and result.success and port.final_state.value == "DRAINED"
else:
    assert result is None
if failure is FailurePoint.LAUNCH_AFTER_CREATE:
    assert port.discovery_requested
"""

DISCOVERY_FAILURE_PROGRAM = """
from alfabetizacao_pipeline.streaming.workflow_orchestrator import (
    FailurePoint, InMemoryWorkflowPort, WorkflowExecutionError, run_guarded_workflow
)
port = InMemoryWorkflowPort(
    failure=FailurePoint.LAUNCH_AFTER_CREATE,
    fail_cleanup=True,
)
try:
    run_guarded_workflow(port)
except WorkflowExecutionError as error:
    assert error.failure is FailurePoint.LAUNCH_AFTER_CREATE
else:
    raise AssertionError("primary launch error was masked")
assert port.discovery_requested
assert not port.job_id_known
"""

PAGINATION_PROGRAM = """
from alfabetizacao_pipeline.streaming.workflow_orchestrator import simulate_paginated_discovery

second_page = simulate_paginated_discovery(
    active_jobs_before_target=101,
    target_matches=True,
    repeated_page_token=False,
)
assert second_page.found
assert second_page.pages_scanned == 2

mismatch = simulate_paginated_discovery(
    active_jobs_before_target=101,
    target_matches=False,
    repeated_page_token=False,
)
assert not mismatch.found

repeated = simulate_paginated_discovery(
    active_jobs_before_target=101,
    target_matches=True,
    repeated_page_token=True,
)
assert not repeated.found
assert repeated.repeated_token_detected
assert repeated.pages_scanned == 2
"""


@pytest.mark.parametrize(
    "failure",
    ["launch_after_create", "producer", "stage", "raw_stale", "merge", "backlog", "none"],
)
def test_every_path_reaches_terminal_cleanup(failure: str) -> None:
    # Given a launched workflow with success or one injected failure
    # When guarded orchestration executes in an isolated interpreter
    completed = subprocess.run(
        [sys.executable, "-c", ORCHESTRATOR_PROGRAM, failure],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then no path leaves a RUNNING job or masks the expected failure
    assert completed.returncode == 0, completed.stderr


def test_cleanup_failure_does_not_mask_primary_error() -> None:
    # Given a producer failure followed by a cleanup API failure
    program = ORCHESTRATOR_PROGRAM.replace(
        "port = InMemoryWorkflowPort(failure=failure)",
        "port = InMemoryWorkflowPort(failure=failure, fail_cleanup=True)",
    ).replace(
        "assert port.cleanup_waited",
        "assert not port.cleanup_waited",
    )

    # When guarded orchestration preserves the producer error
    completed = subprocess.run(
        [sys.executable, "-c", program, "producer"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then cancellation is terminal and the cleanup error never masks the cause
    assert completed.returncode == 0, completed.stderr


def test_discovery_failure_does_not_mask_ambiguous_launch_error() -> None:
    # Given a post-creation timeout followed by discovery failure
    # When guarded orchestration executes the ambiguous cleanup path
    completed = subprocess.run(
        [sys.executable, "-c", DISCOVERY_FAILURE_PROGRAM],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then the original launch error remains observable
    assert completed.returncode == 0, completed.stderr


def test_paginated_discovery_finds_page_two_and_stops_repeated_token() -> None:
    # Given more than one hundred active jobs and exact target on page two
    # When discovery also receives a repeated-token adversarial response
    completed = subprocess.run(
        [sys.executable, "-c", PAGINATION_PROGRAM],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then exact target is found across pages and repeated token stops safely
    assert completed.returncode == 0, completed.stderr
