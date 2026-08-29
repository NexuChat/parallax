from demo.sites.admin import AdminSite
from demo.sites.base import Request


def request(path: str, role: str = "anon", **query: str) -> Request:
    cookies = {} if role == "anon" else {"session": role}
    return Request(path=path, query=query, cookies=cookies)


def test_admin_declares_exactly_the_three_deliberate_plants() -> None:
    site = AdminSite()
    assert [(plant.defect, plant.axis, plant.route) for plant in site.planted] == [
        ("inversion", "privilege", "/reports"),
        ("drift", "locale", "/exports"),
        ("dead", "baseline", "/legacy"),
    ]


def test_intentional_inversion_owner_is_locked_out_while_member_reaches_reports() -> None:
    site = AdminSite()
    assert site.handle(request("/reports", "owner")).status == 302
    assert site.handle(request("/reports", "member")).status == 200


def test_intentional_locale_drift_exports_disappear_in_arabic() -> None:
    site = AdminSite()
    assert site.handle(request("/exports", "member", lang="en")).status == 200
    assert site.handle(request("/exports", "member", lang="ar")).status == 404


def test_intentional_dead_legacy_link_is_unreachable_for_everyone() -> None:
    site = AdminSite()
    for role in ("anon", "member", "owner"):
        for lang in ("en", "ar"):
            assert site.handle(request("/legacy", role, lang=lang)).status == 404


def test_home_and_users_keep_their_correct_baseline_access() -> None:
    site = AdminSite()
    assert all(site.handle(request("/", role)).status == 200 for role in ("anon", "member", "owner"))
    assert site.handle(request("/users")).status == 302
    assert site.handle(request("/users", "member")).status == 200
    assert site.handle(request("/users", "owner")).status == 200
