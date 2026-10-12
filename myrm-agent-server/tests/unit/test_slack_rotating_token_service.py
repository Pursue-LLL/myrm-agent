"""Unit tests for SlackRotatingTokenService."""

from app.schemas.slack_rotating_token import (
    ClassifySlackTokenRequest,
    ClassifySlackTokenResponse,
    InspectSlackScopeRequest,
    InspectSlackScopeResponse,
    SlackTokenCategoryDto,
    SlackTokenTypeDto,
)
from app.services.security.slack_rotating_token_service import (
    SlackRotatingTokenService,
    slack_rotating_token_service,
)


def test_service_classify_rotating_token() -> None:
    service = SlackRotatingTokenService()
    req = ClassifySlackTokenRequest(
        token_or_auth_header="Bearer xoxe.xoxb-12345-rotating-bot"
    )
    res: ClassifySlackTokenResponse = service.classify_token(req)

    assert res.token_type == SlackTokenTypeDto.BOT
    assert res.category == SlackTokenCategoryDto.ROTATING
    assert res.is_rotating is True
    assert res.prefix_matched == "xoxe.xoxb-"
    assert res.normalized_token == "xoxe.xoxb-12345-rotating-bot"
    assert res.is_bearer_wrapped is True


def test_service_classify_user_and_refresh() -> None:
    service = SlackRotatingTokenService()

    # User rotating
    req_u = ClassifySlackTokenRequest(token_or_auth_header="xoxe.xoxp-98765")
    res_u = service.classify_token(req_u)
    assert res_u.token_type == SlackTokenTypeDto.USER
    assert res_u.category == SlackTokenCategoryDto.ROTATING
    assert res_u.is_rotating is True

    # Refresh
    req_r = ClassifySlackTokenRequest(token_or_auth_header="xoxe.xoxr-refresh-token")
    res_r = service.classify_token(req_r)
    assert res_r.token_type == SlackTokenTypeDto.REFRESH
    assert res_r.category == SlackTokenCategoryDto.REFRESH
    assert res_r.is_rotating is False


def test_service_inspect_scopes() -> None:
    service = SlackRotatingTokenService()

    # Bot scope top-level
    req_bot = InspectSlackScopeRequest(
        token_type=SlackTokenTypeDto.BOT,
        metadata={"scope": "chat:write, channels:read"},
    )
    res_bot: InspectSlackScopeResponse = service.inspect_scopes(req_bot)
    assert res_bot.token_type == SlackTokenTypeDto.BOT
    assert res_bot.resolved_scopes == ["channels:read", "chat:write"]
    assert res_bot.source_field == "scope"

    # User scope in authed_user
    req_user = InspectSlackScopeRequest(
        token_type=SlackTokenTypeDto.USER,
        metadata={
            "authed_user": {
                "scope": ["chat:write", "users:read"],
            }
        },
    )
    res_user: InspectSlackScopeResponse = service.inspect_scopes(req_user)
    assert res_user.token_type == SlackTokenTypeDto.USER
    assert res_user.resolved_scopes == ["chat:write", "users:read"]
    assert res_user.source_field == "authed_user.scope"


def test_singleton_instance() -> None:
    assert isinstance(slack_rotating_token_service, SlackRotatingTokenService)
