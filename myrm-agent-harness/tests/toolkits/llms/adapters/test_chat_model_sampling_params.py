"""Sampling options set on the chat model reach the request parameters of every wire.

OpenAI-shaped bodies also get them through the factory's extra_body mirror; the wires with their own protocol read the
typed parameters only, so the model has to hand them over.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model import TransportChatModel


def _model(**kwargs: object) -> TransportChatModel:
    return TransportChatModel.model_construct(client=MagicMock(), model="gemini/gemini-2.5-flash", **kwargs)


def test_top_p_and_top_k_are_request_parameters() -> None:
    params = _model(top_p=0.9, top_k=40)._default_params
    assert (params["top_p"], params["top_k"]) == (0.9, 40)


@pytest.mark.parametrize("name", ["top_p", "top_k"])
def test_unset_sampling_option_is_not_sent(name: str) -> None:
    assert name not in _model()._default_params
