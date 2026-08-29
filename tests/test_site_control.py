import re

from demo.sites.base import Request
from demo.sites.control import ControlSite


def page(site: ControlSite, path: str, role: str = "anon", **query: str) -> str:
    cookies = {} if role == "anon" else {"session": role}
    response = site.handle(Request(path=path, query=query, cookies=cookies))
    assert response.status == 200
    return response.body.decode()


def stylesheet(markup: str) -> str:
    return re.search(r"<style>(.*?)</style>", markup).group(1)


def test_control_declares_no_planted_findings() -> None:
    assert ControlSite().planted == []


def test_control_privilege_narrows_properly_owner_reaches_reports_member_cannot() -> None:
    site = ControlSite()
    assert site.handle(Request(path="/reports", cookies={"session": "owner"})).status == 200
    assert site.handle(Request(path="/reports", cookies={"session": "member"})).status == 302
    assert site.handle(Request(path="/team", cookies={"session": "member"})).status == 200


def test_control_arabic_page_declares_rtl_and_uses_logical_layout() -> None:
    markup = page(ControlSite(), "/", lang="ar")
    assert '<html lang="ar" dir="rtl">' in markup
    assert "padding-inline" in markup and "margin-inline" in markup
    assert "padding-left" not in markup and "margin-right" not in markup
    assert "نظرة عامة" in markup


def test_control_dark_and_light_only_change_colour_declarations() -> None:
    site = ControlSite()
    light, dark = stylesheet(page(site, "/", theme="light")), stylesheet(page(site, "/", theme="dark"))
    variable_prefix = r":root\{--bg:[^;]+;--ink:[^;]+;--wash:[^;]+;--accent:[^;]+;--card:[^;]+;--muted:[^;]+;--line:[^}]+\}"
    assert re.sub(variable_prefix, ":root{COLORS}", light) == re.sub(variable_prefix, ":root{COLORS}", dark)
    assert light != dark


def test_control_has_no_raw_i18n_keys_and_all_declared_taps_are_44px() -> None:
    site = ControlSite()
    for lang in ("en", "ar"):
        markups = (
            page(site, "/", lang=lang),
            page(site, "/team", "member", lang=lang),
            page(site, "/reports", "owner", lang=lang),
            page(site, "/login", lang=lang),
        )
        for markup in markups:
            assert "home_title" not in markup and "report_text" not in markup and "login_title" not in markup
    css = stylesheet(page(site, "/"))
    for selector in site.tap_targets:
        blocks = re.findall(re.escape(selector) + r"\{([^}]*)\}", css)
        heights = [int(match.group(1)) for block in blocks if (match := re.search(r"min-block-size:(\d+)px", block))]
        assert heights and min(heights) >= 44


def test_mounted_pages_keep_links_and_actions_within_control() -> None:
    site = ControlSite()
    for path, cookies in (("/", {}), ("/team", {"session": "member"})):
        markup = site.handle(Request(path=path, mount="/control", cookies=cookies)).body.decode()
        assert all(url.startswith("/control") for url in re.findall(r'(?:href|action)=["\']?([^"\' >]+)', markup))


def test_mounted_protected_route_redirects_to_mounted_login() -> None:
    response = ControlSite().handle(Request(path="/team", mount="/control"))

    assert response.headers["Location"] == "/control/login"
