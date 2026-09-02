import re
from pathlib import Path


def test_service_account_iam_when_bootstrap_creates_identities() -> None:
    bootstrap = Path("infra/bootstrap/main.tf").read_text(encoding="utf-8")

    expected_targets = (
        "service_account_id = google_service_account.cloud_build.name",
        "service_account_id = google_service_account.ci.name",
    )

    assert all(target in bootstrap for target in expected_targets)
    assert 'service_account_id = "projects/${var.project_id}/serviceAccounts/' not in bootstrap


def test_identity_resources_when_bootstrap_enables_required_apis() -> None:
    bootstrap = Path("infra/bootstrap/main.tf").read_text(encoding="utf-8")

    service_accounts = ("terraform_deployer", "ci", "cloud_build")
    iam_api_dependency = 'depends_on = [google_project_service.required["iam.googleapis.com"]]'

    for account in service_accounts:
        match = re.search(
            rf'resource "google_service_account" "{account}" \{{(?P<body>.*?)\n\}}',
            bootstrap,
            flags=re.DOTALL,
        )
        assert match is not None
        assert iam_api_dependency in match.group("body")
    wif = re.search(
        r'resource "google_iam_workload_identity_pool" "github" \{(?P<body>.*?)\n\}',
        bootstrap,
        flags=re.DOTALL,
    )
    assert wif is not None
    assert 'google_project_service.required["sts.googleapis.com"]' in wif.group("body")
    assert 'google_project_service.required["iamcredentials.googleapis.com"]' in wif.group("body")


def test_project_and_billing_iam_when_bootstrap_enables_required_apis() -> None:
    bootstrap = Path("infra/bootstrap/main.tf").read_text(encoding="utf-8")

    project_bindings = ("deployer", "ci", "cloud_build")
    required_api = (
        'depends_on = [google_project_service.required["cloudresourcemanager.googleapis.com"]]'
    )

    for binding in project_bindings:
        match = re.search(
            rf'resource "google_project_iam_member" "{binding}" \{{(?P<body>.*?)\n\}}',
            bootstrap,
            flags=re.DOTALL,
        )
        assert match is not None
        body = match.group("body")
        assert required_api in body
    billing_kind = "google_billing_account_iam_member"
    billing_name = "deployer_costs_manager"
    billing_pattern = r'resource "{}" "{}" \{{(?P<body>.*?)\n\}}'
    billing_resource = billing_pattern.format(
        billing_kind,
        billing_name,
    )
    billing = re.search(
        billing_resource,
        bootstrap,
        flags=re.DOTALL,
    )
    assert billing is not None
    billing_body = billing.group("body")
    assert 'google_project_service.required["cloudbilling.googleapis.com"]' in billing_body


def test_ci_build_role_when_bootstrap_grants_wif_permissions() -> None:
    bootstrap = Path("infra/bootstrap/main.tf").read_text(encoding="utf-8")

    assert "roles/cloudbuild.builds." + "editor" not in bootstrap
    assert '"cloudbuild.builds.create"' in bootstrap
    assert '"cloudbuild.builds.get"' in bootstrap
    assert '"cloudbuild.builds.list"' in bootstrap


def test_ci_build_role_waits_for_apis_used_by_its_permissions() -> None:
    bootstrap = Path("infra/bootstrap/main.tf").read_text(encoding="utf-8")
    match = re.search(
        r'resource "google_project_iam_custom_role" "ci_cloud_build_submit" \{(?P<body>.*?)\n\}',
        bootstrap,
        flags=re.DOTALL,
    )

    assert match is not None
    body = match.group("body")
    assert 'google_project_service.required["iam.googleapis.com"]' in body
    assert 'google_project_service.required["cloudbuild.googleapis.com"]' in body
