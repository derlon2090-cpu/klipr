import pytest
from pydantic import ValidationError

from app.main import CreatorSuggestionRequest, normalize_live_url


def test_creator_suggestion_normalizes_name_and_platform():
    payload = CreatorSuggestionRequest(
        creator_name="  Arab   Creator  ",
        platform="Twitch",
        channel_url="https://twitch.tv/arabcreator",
    )
    assert payload.creator_name == "Arab Creator"
    assert payload.platform == "twitch"


@pytest.mark.parametrize("platform", ["youtube", "", "tiktok"])
def test_creator_suggestion_rejects_unsupported_platform(platform):
    with pytest.raises(ValidationError):
        CreatorSuggestionRequest(creator_name="Creator", platform=platform)


def test_creator_suggestion_channel_url_uses_safe_provider_validation():
    assert normalize_live_url("https://kick.com/creator") == (
        "kick",
        "https://kick.com/creator",
    )
