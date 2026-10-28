"""Teams reacts through the Bot Framework connector with a reaction ID, added by PUT and removed by DELETE.

The fake connector enforces the contract of the official Teams SDK (``microsoft-teams-api`` ``ReactionClient``:
``PUT``/``DELETE`` ``/v3/conversations/{conversation}/activities/{activity}/reactions/{reactionType}``) and the
reaction IDs of the Teams Emoji Reactions Reference, so a request the connector would refuse fails here too. A glyph
without an ID is never sent as another reaction, and a removal takes down what this channel put on the message.
"""

from __future__ import annotations

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.msteams import MSTeamsChannel
from app.channels.providers.msteams.helpers import EMOJI_TO_TEAMS_REACTION, encode_message_key

SERVICE_URL = "https://smba.example.net/emea"
CONVERSATION = "19:conv@thread.tacv2"
ACTIVITY = "1700000000000"

# glyph -> reaction ID, copied from the Teams Emoji Reactions Reference.
OFFICIAL_IDS = {
    "\U0001f440": "1f440_eyes",
    "\U0001f914": "think",
    "\U0001f4ad": "1f4ad_thoughtballoon",
    "\U0001f9e0": "1f9e0_brain",
    "\u2728": "2728_sparkles",
    "\u2705": "2705_whiteheavycheckmark",
    "\U0001f44d": "like",
    "\U0001f389": "1f389_partypopper",
    "\U0001f4af": "1f4af_hundredpointssymbol",
    "\U0001f64c": "handsinair",
    "\u274c": "274c_crossmark",
    "\u26a0": "26a0_warningsign",
    "\U0001f494": "brokenheart",
    "\U0001f6ab": "1f6ab_noentrysign",
    "\u26d4": "26d4_noentry",
    "\U0001f635": "1f635_dizzyface",
    "\U0001f622": "cry",
}
_PATH_PREFIX = f"/emea/v3/conversations/{CONVERSATION}/activities/{ACTIVITY}/reactions/"


class _FakeConnector:
    """Serves the login endpoint and records the reaction calls the connector would accept."""

    def __init__(self, status: int = 204) -> None:
        self.calls: list[tuple[str, str]] = []
        self._status = status

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        reaction = request.url.path.removeprefix(_PATH_PREFIX)
        accepted = (
            request.method in {"PUT", "DELETE"}
            and request.url.path.startswith(_PATH_PREFIX)
            and reaction in OFFICIAL_IDS.values()
            and request.headers.get("authorization") == "Bearer tok"
        )
        if not accepted:
            return httpx.Response(405)
        self.calls.append((request.method, reaction))
        return httpx.Response(self._status)


def _channel(
    connector: _FakeConnector | None = None, transport: httpx.MockTransport | None = None
) -> tuple[MSTeamsChannel, _FakeConnector]:
    connector = connector or _FakeConnector()
    ch = MSTeamsChannel(app_id="test_app_id", app_password="test_app_password")
    client = httpx.AsyncClient(transport=transport or httpx.MockTransport(connector.handle))
    ch._http = client
    ch._api._http = client
    ch._api.cache_service_url(CONVERSATION, SERVICE_URL)
    return ch, connector


class TestDeclaredVocabulary:
    @pytest.mark.parametrize("glyph", list(OFFICIAL_IDS))
    def test_accepts_every_glyph_that_has_a_teams_id(self, glyph: str) -> None:
        assert MSTeamsChannel.capabilities.accepts_reaction(glyph)

    @pytest.mark.parametrize("glyph", ["\u23f3", "\U0001f525", "\U0001f44e"])
    def test_rejects_glyphs_without_a_teams_id(self, glyph: str) -> None:
        assert not MSTeamsChannel.capabilities.accepts_reaction(glyph)

    def test_the_vocabulary_is_the_official_ids(self) -> None:
        assert EMOJI_TO_TEAMS_REACTION == OFFICIAL_IDS


class TestReactToMessage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("glyph", "reaction_id"), list(OFFICIAL_IDS.items()))
    async def test_a_glyph_is_put_under_its_reaction_id(self, glyph: str, reaction_id: str) -> None:
        ch, connector = _channel()
        await ch.react_to_message(CONVERSATION, ACTIVITY, glyph)
        assert connector.calls == [("PUT", reaction_id)]

    @pytest.mark.asyncio
    async def test_the_status_reactions_keep_their_own_meaning(self) -> None:
        ch, connector = _channel()
        for glyph in ("\U0001f440", "\u2705", "\u274c"):
            await ch.react_to_message(CONVERSATION, ACTIVITY, glyph)
        assert [reaction for _, reaction in connector.calls] == ["1f440_eyes", "2705_whiteheavycheckmark", "274c_crossmark"]

    @pytest.mark.asyncio
    async def test_a_message_key_carries_its_own_service_url_and_conversation(self) -> None:
        ch, connector = _channel()
        key = encode_message_key(ACTIVITY, SERVICE_URL, CONVERSATION)
        await ch.react_to_message("unknown-chat", key, "\U0001f440")
        assert connector.calls == [("PUT", "1f440_eyes")]

    @pytest.mark.asyncio
    async def test_a_glyph_without_an_id_sends_nothing(self) -> None:
        ch, connector = _channel()
        await ch.react_to_message(CONVERSATION, ACTIVITY, "\U0001f525")
        assert connector.calls == []

    @pytest.mark.asyncio
    async def test_an_unknown_service_url_sends_nothing(self) -> None:
        ch, connector = _channel()
        await ch.react_to_message("unknown-chat", ACTIVITY, "\U0001f440")
        await ch.react_to_message("unknown-chat", ACTIVITY, "")
        assert connector.calls == []

    @pytest.mark.asyncio
    async def test_an_empty_emoji_deletes_the_reaction_that_was_put(self) -> None:
        ch, connector = _channel()
        await ch.react_to_message(CONVERSATION, ACTIVITY, "\U0001f440")
        await ch.react_to_message(CONVERSATION, ACTIVITY, "")
        assert connector.calls == [("PUT", "1f440_eyes"), ("DELETE", "1f440_eyes")]

    @pytest.mark.asyncio
    async def test_an_empty_emoji_sends_nothing_when_nothing_was_put(self) -> None:
        ch, connector = _channel()
        await ch.react_to_message(CONVERSATION, ACTIVITY, "")
        assert connector.calls == []

    @pytest.mark.asyncio
    async def test_a_reaction_is_deleted_only_once(self) -> None:
        ch, connector = _channel()
        await ch.react_to_message(CONVERSATION, ACTIVITY, "\u2705")
        await ch.react_to_message(CONVERSATION, ACTIVITY, "")
        await ch.react_to_message(CONVERSATION, ACTIVITY, "")
        assert [method for method, _ in connector.calls] == ["PUT", "DELETE"]

    @pytest.mark.asyncio
    async def test_a_refused_reaction_raises_and_is_not_remembered(self) -> None:
        refused = _FakeConnector()

        def refuse(request: httpx.Request) -> httpx.Response:
            if request.url.host == "login.microsoftonline.com":
                return refused.handle(request)
            return httpx.Response(403, text="forbidden")

        ch, connector = _channel(transport=httpx.MockTransport(refuse))
        with pytest.raises(ChannelSendError):
            await ch.react_to_message(CONVERSATION, ACTIVITY, "\U0001f440")
        await ch.react_to_message(CONVERSATION, ACTIVITY, "")
        assert connector.calls == []

    @pytest.mark.asyncio
    async def test_a_transport_error_surfaces_as_a_send_error(self) -> None:
        down = _FakeConnector()

        def unreachable(request: httpx.Request) -> httpx.Response:
            if request.url.host == "login.microsoftonline.com":
                return down.handle(request)
            raise httpx.ConnectError("net", request=request)

        ch, _ = _channel(transport=httpx.MockTransport(unreachable))
        with pytest.raises(ChannelSendError, match="ConnectError"):
            await ch.react_to_message(CONVERSATION, ACTIVITY, "\U0001f440")
