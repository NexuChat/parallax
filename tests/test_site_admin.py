import re

from demo.sites.admin import AdminSite
from demo.sites.base import Request


def request(path: str, role: str = "anon", **query: str) -> Request:
    return Request(path=path, query=query, cookies={} if role == "anon" else {"session": role})


def test_admin_declares_exactly_the_three_deliberate_plants() -> None:
    assert [(item.defect, item.axis, item.route) for item in AdminSite().planted] == [("inversion", "privilege", "/reports"), ("drift", "locale", "/exports"), ("dead", "baseline", "/legacy")]


def test_intentional_plants_keep_their_declared_route_behaviour() -> None:
    site = AdminSite()
    assert site.handle(request("/reports", "owner")).status == 302
    assert site.handle(request("/reports", "member")).status == 200
    assert site.handle(request("/exports", "member", lang="en")).status == 200
    assert site.handle(request("/exports", "member", lang="ar")).status == 404
    assert all(site.handle(request("/legacy", role, lang=lang)).status == 404 for role in ("anon", "member", "owner") for lang in ("en", "ar"))


def test_home_and_users_keep_their_correct_baseline_access() -> None:
    site = AdminSite()
    assert all(site.handle(request("/", role)).status == 200 for role in ("anon", "member", "owner"))
    assert site.handle(request("/users")).status == 302
    assert all(site.handle(request("/users", role)).status == 200 for role in ("member", "owner"))


def test_product_pages_render_real_operational_data() -> None:
    site = AdminSite()
    home = site.handle(request("/", "owner")).body.decode()
    users = site.handle(request("/users", "owner")).body.decode()
    reports = site.handle(request("/reports", "member")).body.decode()
    exports = site.handle(request("/exports", "owner")).body.decode()
    assert "System status" in home and "99.98%" in home and "Recent events" in home
    assert "ada@northstar.test" in users and users.count("<tr>") >= 5 and "Invite user" in users
    assert "Weekly operations summary" in reports and "PDF" in reports
    assert "EX-4821" in exports and "Processing" in exports


def test_arabic_home_and_users_are_translated_and_rtl() -> None:
    site = AdminSite()
    home = site.handle(request("/", "owner", lang="ar")).body.decode()
    users = site.handle(request("/users", "owner", lang="ar")).body.decode()
    assert 'dir="rtl"' in home and "حالة الأنظمة" in home
    assert "الأشخاص الذين لديهم صلاحية" in users and "البريد الإلكتروني" in users


def test_login_sets_session_cookie_and_mounted_links_stay_within_admin() -> None:
    site = AdminSite()
    logged_in = site.handle(Request(method="POST", path="/login", mount="/admin", body=b"username=owner&password=owner-pass"))
    assert logged_in.status == 302 and "session=owner" in logged_in.headers["Set-Cookie"]
    markup = site.handle(Request(path="/users", mount="/admin", cookies={"session": "owner"})).body.decode()
    assert all(url.startswith("/admin") for url in re.findall(r'(?:href|action)="([^"]+)', markup))
    assert site.handle(Request(path="/users", mount="/admin")).headers["Location"] == "/admin/login"


def test_declared_accounts_authenticate_against_admin_login() -> None:
    site = AdminSite()
    for account in site.accounts:
        response = site.handle(Request(method="POST", path="/login", body=f"username={account.email}&password={account.password}".encode()))
        assert response.status == 302 and "Set-Cookie" in response.headers
