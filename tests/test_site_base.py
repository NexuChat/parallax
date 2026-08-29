import pytest

from sites.base import Request


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, "en"),
        ({"accept-language": "en-US,en;q=0.9"}, "en"),
        ({"accept-language": "ar-SA,ar;q=0.9,en-US;q=0.8"}, "en"),
        ({"accept-language": "ar"}, "ar"),
        ({"accept-language": "ar-SA,ar;q=0.9"}, "ar"),
        ({"accept-language": "ar--SA"}, "en"),
    ],
)
def test_request_language_from_accept_language(headers: dict[str, str], expected: str) -> None:
    assert Request(headers=headers).lang == expected


def test_request_query_language_beats_accept_language() -> None:
    assert Request(query={"lang": "ar"}, headers={"accept-language": "en-US"}).lang == "ar"


def test_request_cookie_language_beats_accept_language() -> None:
    assert Request(cookies={"lang": "ar"}, headers={"accept-language": "en-US"}).lang == "ar"
