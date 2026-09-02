import subprocess
import sys
from pathlib import Path

RAW_ARCHIVE_GUARD = """
import sys
import yaml

workflow = yaml.safe_load(sys.stdin.read())
main_steps = {
    next(iter(step)): next(iter(step.values()))
    for step in workflow["main"]["steps"]
}
guarded_steps = {
    next(iter(step)): next(iter(step.values()))
    for step in main_steps["guarded_execution"]["try"]["steps"]
}
raw_branch = next(
    branch
    for branch in guarded_steps["independent_stage_checks"]["parallel"]["branches"]
    if "raw_archive_branch" in branch
)
raw_steps = {
    next(iter(step)): next(iter(step.values()))
    for step in raw_branch["raw_archive_branch"]["steps"]
}
raw_call = raw_steps["wait_raw_avro"]
assert raw_call["call"] == "wait_gcs_object"
assert raw_call["args"]["prefix"] == '${raw_archive_prefix + "/"}'
assert "correlation_id" not in raw_call["args"]["prefix"]
assert raw_steps["require_raw"]["switch"][0]["raise"] == (
    "Arquivo raw Avro da janela da execução não apareceu"
)
archive_steps = {
    next(iter(step)): next(iter(step.values()))
    for step in workflow["wait_gcs_object"]["steps"]
}
assert archive_steps["list_objects"]["args"]["maxResults"] == 1000
assert archive_steps["list_objects"]["args"]["pageToken"] == "${page_token}"
assert archive_steps["candidate_is_current"]["switch"][0]["condition"] == (
    "${time.parse(candidate.updated) >= time.parse(window_start)}"
)
assert archive_steps["advance_page"]["next"] == "list_objects"
assert archive_steps["advance_page"]["assign"] == [
    {"page_token": "${next_page_token}"},
    {"page_count": "${page_count + 1}"},
    {"visited_page_tokens": "${list.concat(visited_page_tokens, next_page_token)}"},
]
page_guard = archive_steps["continue_or_decide"]["switch"]
assert {
    '${next_page_token == "" or next_page_token in visited_page_tokens}',
    "${page_count >= max_pages}",
} == {branch["condition"] for branch in page_guard}
monitoring_steps = {
    next(iter(step)): next(iter(step.values()))
    for step in workflow["wait_main_subscription_backlogs"]["steps"]
}
assert monitoring_steps["read_backlog_metric"]["call"] == (
    "googleapis.monitoring.v3.projects.timeSeries.list"
)
assert monitoring_steps["read_backlog_metric"]["args"]["pageSize"] == 1
"""


def test_raw_archive_check_uses_the_physical_gcs_prefix_without_correlation() -> None:
    content = Path("workflows/stream_demo.yaml").read_text(encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-c", RAW_ARCHIVE_GUARD],
        input=content,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
