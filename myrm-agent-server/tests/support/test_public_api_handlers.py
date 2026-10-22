"""The endpoint table tells same-named functions apart, which the OpenAPI operation id cannot."""

from __future__ import annotations

from tests.support.public_api_app import ApiHandler, public_api_handlers


def test_a_handler_is_found_by_its_file_function_method_and_client_path() -> None:
    assert (
        ApiHandler("api/kanban/routes/tasks.py", "create_task", "POST", "/kanban/boards/{board_id}/tasks")
        in public_api_handlers()
    )


def test_files_are_relative_to_app_and_the_api_prefix_is_removed() -> None:
    handlers = public_api_handlers()

    assert handlers
    assert all(h.file.endswith(".py") and not h.file.startswith("/") for h in handlers)
    assert ("POST", "/kanban/boards/{board_id}/tasks") in {(h.method, h.path) for h in handlers}
