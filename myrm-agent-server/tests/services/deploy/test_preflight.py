"""Tests for deploy preflight evaluation."""

from app.services.deploy.deploy_packager import DeployFile
from app.services.deploy.preflight import evaluate_deploy_preflight


def test_evaluate_deploy_preflight_ok_for_index_html() -> None:
    result = evaluate_deploy_preflight(
        {"index.html": DeployFile(path="index.html", content="<h1>Hi</h1>")}
    )
    assert result.deployable is True
    assert result.reason == "OK"


def test_evaluate_deploy_preflight_rejects_tsx_only() -> None:
    result = evaluate_deploy_preflight(
        {"App.tsx": DeployFile(path="App.tsx", content="export default () => null")}
    )
    assert result.deployable is False
    assert result.reason == "CODE_REQUIRES_HTML_ARTIFACT"
    assert result.hint is not None
