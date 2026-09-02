from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class JobPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True)

    id: str
    name: str
    labels: dict[str, str] = Field(default_factory=dict)


class PagePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True)

    jobs: tuple[JobPayload, ...] = ()
    next_page_token: str = Field(default="", alias="nextPageToken")


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveryOutcome:
    matched_job_id: str | None
    scans: int
    pages: int
    repeated_token: bool = False
    duplicate_match: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ScanOutcome:
    matched_job_id: str | None
    pages: int
    retry: bool
    repeated_token: bool = False
    duplicate_match: bool = False


def scan_payloads(pages: Sequence[str], *, job_name: str, run_id: str) -> ScanOutcome:
    match: str | None = None
    visited = {""}
    for page_number, payload in enumerate(pages[:100], start=1):
        try:
            page = PagePayload.model_validate_json(payload)
        except ValidationError:
            return ScanOutcome(matched_job_id=None, pages=page_number, retry=False)
        exact_ids = tuple(
            job.id
            for job in page.jobs
            if job.name == job_name and job.labels.get("run_id") == run_id
        )
        if len(exact_ids) + (match is not None) > 1:
            return ScanOutcome(
                matched_job_id=None,
                pages=page_number,
                retry=False,
                duplicate_match=True,
            )
        if exact_ids:
            match = exact_ids[0]
        token = page.next_page_token
        if token == "":
            return ScanOutcome(matched_job_id=match, pages=page_number, retry=match is None)
        if token in visited:
            return ScanOutcome(
                matched_job_id=None,
                pages=page_number,
                retry=False,
                repeated_token=True,
            )
        visited.add(token)
    return ScanOutcome(matched_job_id=None, pages=min(len(pages), 100), retry=True)


def discover_from_payloads(
    scans: Sequence[Sequence[str]], *, job_name: str, run_id: str
) -> DiscoveryOutcome:
    total_pages = 0
    for scan_number, pages in enumerate(scans[:12], start=1):
        outcome = scan_payloads(pages, job_name=job_name, run_id=run_id)
        total_pages += outcome.pages
        if not outcome.retry:
            return DiscoveryOutcome(
                matched_job_id=outcome.matched_job_id,
                scans=scan_number,
                pages=total_pages,
                repeated_token=outcome.repeated_token,
                duplicate_match=outcome.duplicate_match,
            )
    return DiscoveryOutcome(matched_job_id=None, scans=min(len(scans), 12), pages=total_pages)


def job(job_id: str, *, name: str = "other", run_id: str = "other") -> str:
    return f'{{"id":"{job_id}","name":"{name}","labels":{{"run_id":"{run_id}"}}}}'


def page(jobs: Sequence[str], token: str = "") -> str:
    return f'{{"jobs":[{",".join(jobs)}],"nextPageToken":"{token}"}}'


def test_payload_harness_finds_unique_match_after_one_hundred_jobs() -> None:
    first = page([job(f"other-{index}") for index in range(100)], "page-2")
    second = page([job("target-id", name="demo", run_id="run-1")])

    outcome = discover_from_payloads([[first, second]], job_name="demo", run_id="run-1")

    assert outcome == DiscoveryOutcome(matched_job_id="target-id", scans=1, pages=2)


def test_payload_harness_fails_closed_on_token_cycle_and_duplicate_matches() -> None:
    cycle = [[page([], "A"), page([], "B"), page([], "A")]]
    duplicates = [
        [
            page([job("first", name="demo", run_id="run-1")], "next"),
            page([job("second", name="demo", run_id="run-1")]),
        ]
    ]

    cycled = discover_from_payloads(cycle, job_name="demo", run_id="run-1")
    duplicated = discover_from_payloads(duplicates, job_name="demo", run_id="run-1")

    assert cycled == DiscoveryOutcome(matched_job_id=None, scans=1, pages=3, repeated_token=True)
    assert duplicated == DiscoveryOutcome(
        matched_job_id=None, scans=1, pages=2, duplicate_match=True
    )


def test_payload_harness_bounds_scans_and_rejects_malformed_responses() -> None:
    empty_scans = [[page([])]] * 13
    malformed_jobs = [['{"jobs":"not-a-list"}']]
    malformed_token = [['{"jobs":[],"nextPageToken":123}']]

    bounded = discover_from_payloads(empty_scans, job_name="demo", run_id="run-1")
    bad_jobs = discover_from_payloads(malformed_jobs, job_name="demo", run_id="run-1")
    bad_token = discover_from_payloads(malformed_token, job_name="demo", run_id="run-1")

    assert bounded.scans == 12
    assert bounded.pages == 12
    assert bad_jobs.matched_job_id is None
    assert bad_token.matched_job_id is None
