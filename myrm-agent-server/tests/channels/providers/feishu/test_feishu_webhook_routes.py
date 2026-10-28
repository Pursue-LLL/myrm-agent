"""Feishu registers its webhook route on a route registrar and ignores anything else."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.channels.protocols.route_registrar import HttpMethod
from app.channels.providers.feishu import FeishuChannel
from app.channels.testing.route_testing import MockRouteRegistrar


def _channel() -> FeishuChannel:
    return FeishuChannel(app_id="test_app_id", app_secret="test_app_secret", encrypt_key="test_encrypt_key")


def test_the_webhook_route_is_registered_on_a_route_registrar() -> None:
    registrar = MockRouteRegistrar()
    _channel().register_routes(registrar)
    assert [(route.method, route.path) for route in registrar.registered_routes] == [(HttpMethod.POST, "webhook")]


def test_an_object_that_is_not_a_route_registrar_is_ignored() -> None:
    not_a_registrar = MagicMock(spec=[])
    _channel().register_routes(not_a_registrar)
    assert not_a_registrar.mock_calls == []
