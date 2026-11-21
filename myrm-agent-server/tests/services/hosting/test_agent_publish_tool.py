"""What the model is told about ``artifact_publish``: a workspace path in, no artifact id."""

from __future__ import annotations

from app.services.hosting.agent_publish_tool import create_artifact_publish_tool

# The wording is the one measured against real models; change it only together with new evidence.
DESCRIPTION = (
    "Publish a file from the workspace (HTML application, PDF document, Excel spreadsheet, Markdown report, etc.) "
    "to the user's configured hosting target (Vercel or HTTP Webhook) and return the live URL. "
    "The stylesheets, scripts and images a page links to in its folder are published with it. "
    "Pass the workspace path of the file, for example the path you wrote. "
    "Only use when the user explicitly asks to publish, deploy, or get a live link."
)


def test_the_description_asks_for_the_workspace_path_of_a_file() -> None:
    assert create_artifact_publish_tool("chat-1").description == DESCRIPTION


def test_the_model_passes_a_path_and_never_an_artifact_id() -> None:
    schema = create_artifact_publish_tool("chat-1").get_input_jsonschema()

    assert set(schema["properties"]) == {"path", "hosting_target_id", "password"}
    assert schema["required"] == ["path"]
    assert schema["properties"]["path"]["description"] == "Workspace path of the file to publish (for example site/index.html)."
