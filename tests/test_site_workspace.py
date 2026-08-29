"""Direct contract tests for the small-team workspace demo."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

from sites.base import Request
from sites.workspace import WorkspaceSite


def _login(site: WorkspaceSite, email: str) -> dict[str, str]:
    response = site.handle(
        Request(method="POST", path="/login", body=f"email={email}&password=demo".encode())
    )
    return {"session": response.headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]}


def test_anonymous_user_is_redirected_from_settings() -> None:
    response = WorkspaceSite().handle(Request(path="/settings"))

    assert (response.status, response.headers["Location"]) == (302, "/login")


def test_anonymous_user_wrongly_receives_audit_content_as_planted() -> None:
    response = WorkspaceSite().handle(Request(path="/audit"))

    assert response.status == 200
    assert b"Audit log" in response.body


def test_arabic_query_renders_rtl_and_translated_copy() -> None:
    response = WorkspaceSite().handle(Request(path="/", query={"lang": "ar"}))

    assert b'<html lang="ar" dir="rtl">' in response.body
    assert "مساحة عمل الفريق".encode() in response.body


def test_dark_stylesheet_has_header_border_that_light_stylesheet_lacks() -> None:
    site = WorkspaceSite()
    cookies = _login(site, "owner@demo")
    light = site.handle(Request(path="/threads", query={"theme": "light"}, cookies=cookies)).body.decode()
    dark = site.handle(Request(path="/threads", query={"theme": "dark"}, cookies=cookies)).body.decode()

    assert "header{border-block-end:3px solid" not in light
    assert "header{border-block-end:3px solid" in dark


def test_message_posted_in_one_session_is_visible_to_another_session_poll() -> None:
    site = WorkspaceSite()
    owner = _login(site, "owner@demo")
    member = _login(site, "member@demo")
    posted = site.handle(
        Request(method="POST", path="/threads", cookies=owner, body=b"thread=general&message=Visible+to+the+team")
    )
    message_id = int(parse_qs(posted.headers["Location"].split("?", 1)[1])["posted"][0])

    response = site.handle(Request(path="/api/messages", query={"since": str(message_id - 1)}, cookies=member))

    assert any(message["text"] == "Visible to the team" for message in json.loads(response.body)["messages"])


def test_quiet_thread_message_is_stored_but_never_returned_by_poll_as_planted() -> None:
    site = WorkspaceSite()
    owner = _login(site, "owner@demo")
    member = _login(site, "member@demo")
    posted = site.handle(
        Request(method="POST", path="/threads", cookies=owner, body=b"thread=quiet&message=This+will+stay+quiet")
    )
    message_id = int(parse_qs(posted.headers["Location"].split("?", 1)[1])["posted"][0])

    response = site.handle(Request(path="/api/messages", query={"since": str(message_id - 1)}, cookies=member))

    assert all(message["id"] != message_id for message in json.loads(response.body)["messages"])


def test_unknown_path_is_not_found() -> None:
    response = WorkspaceSite().handle(Request(path="/does-not-exist"))

    assert response.status == 404
