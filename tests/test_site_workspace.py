"""Direct contract tests for the shared-team workspace demo."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

from sites.base import Request
from sites.workspace import WorkspaceSite


def _login(site: WorkspaceSite, email: str) -> dict[str, str]:
    response = site.handle(Request(method="POST", path="/login", body=f"email={email}&password=demo".encode()))
    return {"session": response.headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]}


def test_anonymous_user_is_redirected_from_owner_routes() -> None:
    site = WorkspaceSite()
    for path in ("/settings", "/billing"):
        response = site.handle(Request(path=path))
        assert (response.status, response.headers["Location"]) == (302, "/login")


def test_landing_has_activity_proof_and_thread_preview() -> None:
    markup = WorkspaceSite().handle(Request(path="/")).body.decode()
    assert "Live activity" in markup and "1,284" in markup
    assert "Customer notes" in markup and markup.count('class="avatar"') >= 2


def test_signed_in_threads_have_previews_day_grouping_and_composer() -> None:
    site = WorkspaceSite()
    markup = site.handle(Request(path="/threads", cookies=_login(site, "owner@demo"))).body.decode()
    assert "All conversations" in markup and "Today" in markup
    assert 'class="composer-tools"' in markup and 'data-latest=' in markup
    assert "setInterval" in markup and "/api/messages?since=" in markup


def test_owner_pages_have_real_grouped_data() -> None:
    site = WorkspaceSite()
    cookies = _login(site, "owner@demo")
    settings = site.handle(Request(path="/settings", cookies=cookies)).body.decode()
    billing = site.handle(Request(path="/billing", cookies=cookies)).body.decode()
    audit = site.handle(Request(path="/audit")).body.decode()
    assert "Notifications" in settings and "Permissions" in settings
    assert "INV-2026-041" in billing and "Usage this month" in billing
    assert "Avery Kim" in audit and "Changed billing owner" in audit


def test_mounted_pages_keep_links_and_actions_within_workspace() -> None:
    site = WorkspaceSite()
    cookies = _login(site, "owner@demo")
    for path, request_cookies in (("/", {}), ("/threads", cookies), ("/billing", cookies), ("/audit", {})):
        markup = site.handle(Request(path=path, mount="/workspace", cookies=request_cookies)).body.decode()
        assert all(url.startswith("/workspace") for url in re.findall(r'(?:href|action)="([^" >]+)', markup))


def test_mounted_protected_route_redirects_to_mounted_login() -> None:
    response = WorkspaceSite().handle(Request(path="/settings", mount="/workspace"))
    assert response.headers["Location"] == "/workspace/login"


def test_anonymous_user_wrongly_receives_audit_content_as_planted() -> None:
    response = WorkspaceSite().handle(Request(path="/audit"))
    assert response.status == 200 and b"Audit log" in response.body


def test_arabic_query_renders_rtl_and_translated_copy() -> None:
    response = WorkspaceSite().handle(Request(path="/", query={"lang": "ar"}))
    assert b'<html lang="ar" dir="rtl">' in response.body
    assert "مكان أوضح للعمل معًا".encode() in response.body


def test_dark_stylesheet_has_header_border_that_light_stylesheet_lacks() -> None:
    site = WorkspaceSite()
    cookies = _login(site, "owner@demo")
    light = site.handle(Request(path="/threads", query={"theme": "light"}, cookies=cookies)).body.decode()
    dark = site.handle(Request(path="/threads", query={"theme": "dark"}, cookies=cookies)).body.decode()
    assert ".site-header{border-block-end:3px solid" not in light
    assert ".site-header{border-block-end:3px solid" in dark


def test_message_posted_in_one_session_is_visible_to_another_session_poll() -> None:
    site = WorkspaceSite()
    owner, member = _login(site, "owner@demo"), _login(site, "member@demo")
    posted = site.handle(Request(method="POST", path="/threads", cookies=owner, body=b"thread=general&message=Visible+to+the+team"))
    message_id = int(parse_qs(posted.headers["Location"].split("?", 1)[1])["posted"][0])
    response = site.handle(Request(path="/api/messages", query={"since": str(message_id - 1)}, cookies=member))
    assert any(message["text"] == "Visible to the team" for message in json.loads(response.body)["messages"])


def test_quiet_thread_message_is_stored_but_never_returned_by_poll_as_planted() -> None:
    site = WorkspaceSite()
    owner, member = _login(site, "owner@demo"), _login(site, "member@demo")
    posted = site.handle(Request(method="POST", path="/threads", cookies=owner, body=b"thread=quiet&message=This+will+stay+quiet"))
    message_id = int(parse_qs(posted.headers["Location"].split("?", 1)[1])["posted"][0])
    response = site.handle(Request(path="/api/messages", query={"since": str(message_id - 1)}, cookies=member))
    assert all(message["id"] != message_id for message in json.loads(response.body)["messages"])


def test_unknown_path_is_not_found() -> None:
    assert WorkspaceSite().handle(Request(path="/does-not-exist")).status == 404
