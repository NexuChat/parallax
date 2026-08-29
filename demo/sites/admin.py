"""A deliberately flawed internal console.

Seeded accounts are ``owner / owner-pass`` and ``member / member-pass``.  POST
those ``username`` and ``password`` values to ``/login`` to receive the session
cookie used by this small, stateless demo.  ``anon`` is represented by no
session cookie.
"""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from .base import Planted, Request, Response


class AdminSite:
    name = "admin"
    title = "Operations desk"
    planted = [
        Planted("inversion", "privilege", "/reports", "Owners are redirected while members may read reports."),
        Planted("drift", "locale", "/exports", "The English-only export route disappears in Arabic."),
        Planted("dead", "baseline", "/legacy", "A navigation link points to a route which never resolves."),
    ]
    tap_targets = (".tap",)

    _words = {
        "en": {"brand": "Operations desk", "home": "Overview", "users": "Users", "reports": "Reports", "exports": "Exports", "legacy": "Legacy archive", "sign_in": "Sign in", "sign_out": "Sign out", "welcome": "Operations, in view.", "intro": "A quiet place to keep the team moving.", "users_title": "People with access", "reports_title": "Weekly reports", "exports_title": "Data exports", "login_title": "Sign in to the desk", "username": "Username", "password": "Password", "submit": "Continue", "bad_login": "Those details did not match an account.", "role": "Current role", "owner": "Owner", "member": "Member", "anon": "Guest", "note": "Review access before sharing exports.", "active": "Active seats", "deployments": "Deployments today", "alerts": "Open alerts", "events": "Recent events", "last_seen": "Last seen", "person": "Person", "status": "Status", "footer": "Operations desk · Access and activity for the whole team."},
        "ar": {"brand": "لوحة العمليات", "home": "نظرة عامة", "users": "المستخدمون", "reports": "التقارير", "exports": "التصديرات", "legacy": "الأرشيف القديم", "sign_in": "تسجيل الدخول", "sign_out": "تسجيل الخروج", "welcome": "العمليات أمامك.", "intro": "مكان هادئ يحافظ على سير عمل الفريق.", "users_title": "الأشخاص الذين لديهم صلاحية", "reports_title": "التقارير الأسبوعية", "exports_title": "تصديرات البيانات", "login_title": "تسجيل الدخول إلى لوحة العمليات", "username": "اسم المستخدم", "password": "كلمة المرور", "submit": "متابعة", "bad_login": "هذه البيانات لا تطابق حساباً.", "role": "الدور الحالي", "owner": "المالك", "member": "عضو", "anon": "زائر", "note": "راجع الصلاحية قبل مشاركة التصديرات.", "active": "المقاعد النشطة", "deployments": "إطلاقات اليوم", "alerts": "تنبيهات مفتوحة", "events": "الأحداث الأخيرة", "last_seen": "آخر ظهور", "person": "الشخص", "status": "الحالة", "footer": "لوحة العمليات · الوصول والنشاط للفريق كله."},
    }

    def _role(self, request: Request) -> str:
        return request.cookies.get("session", "anon") if request.cookies.get("session") in {"owner", "member"} else "anon"

    def _style(self, theme: str) -> str:
        colors = ("#f8f7f2", "#17211f", "#e4f0ea", "#176b56", "#ffffff", "#53645f", "#c8d8d0") if theme == "light" else ("#11201c", "#eff8f2", "#1b3029", "#87d8b6", "#182a25", "#b8c9c1", "#38534a")
        return f"""<style>:root{{--bg:{colors[0]};--ink:{colors[1]};--wash:{colors[2]};--accent:{colors[3]};--card:{colors[4]};--muted:{colors[5]};--line:{colors[6]}}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Georgia,'Noto Naskh Arabic',serif;line-height:1.5}}.shell{{max-inline-size:1120px;margin-inline:auto;padding:clamp(16px,4vw,52px)}}header,footer{{border-block-end:1px solid var(--line);padding-block-end:18px}}footer{{border-block-start:1px solid var(--line);border-block-end:0;padding-block:24px;color:var(--muted);font-size:.9rem}}.mast{{display:flex;align-items:center;justify-content:space-between;gap:16px}}.brand{{font-size:1.12rem;font-weight:bold;letter-spacing:.04em}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin-block-start:18px}}a,.tap{{color:inherit}}.tap{{display:inline-flex;align-items:center;justify-content:center;min-block-size:44px;padding-inline:15px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:transparent;font:inherit}}.tap:hover,.tap:focus-visible{{background:var(--wash);outline:3px solid var(--accent);outline-offset:2px}}main{{padding-block:clamp(34px,6vw,66px)}}.eyebrow{{color:var(--accent);font-weight:bold;text-transform:uppercase;letter-spacing:.1em}}h1{{font-size:clamp(2.2rem,6vw,4.4rem);line-height:.95;max-inline-size:15ch;margin:12px 0}}p{{max-inline-size:62ch}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:16px;margin-block-start:28px}}.card,.events,table{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;min-inline-size:0}}.metric strong{{display:block;font:700 2rem/1 system-ui,sans-serif;margin-block:8px}}.metric span,.muted{{color:var(--muted)}}.events{{margin-block-start:28px}}.events ul{{margin:0;padding-inline-start:20px}}.events li{{padding-block:8px;border-block-end:1px solid var(--line)}}.events li:last-child{{border:0}}table{{width:100%;border-collapse:separate;border-spacing:0;padding:0;overflow:hidden;margin-block-start:28px;font-variant-numeric:tabular-nums}}th,td{{padding:14px;text-align:start;border-block-end:1px solid var(--line)}}tr:last-child td{{border:0}}th{{font:700 .78rem/1 system-ui,sans-serif;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}}label{{display:grid;gap:7px;font-weight:bold}}input{{min-block-size:44px;inline-size:100%;border:1px solid var(--line);border-radius:8px;padding-inline:12px;font:inherit;background:var(--card);color:var(--ink)}}form{{display:grid;gap:18px;max-inline-size:420px}}button{{cursor:pointer}}@media (max-width:420px){{.shell{{padding:16px}}.mast{{align-items:flex-start;flex-direction:column}}table{{font-size:.85rem}}th,td{{padding:10px 7px}}}}</style>"""

    def _page(self, request: Request, content: str, page: str) -> Response:
        lang = request.lang
        w = self._words[lang]
        role = self._role(request)
        query = f"?lang={lang}&theme={request.theme}"
        nav = "".join(f'<a class="tap" href="{request.mount}{path}{query}">{w[key]}</a>' for path, key in (("/", "home"), ("/users", "users"), ("/reports", "reports"), ("/exports", "exports"), ("/legacy", "legacy")))
        account = f'<a class="tap" href="{request.mount}/login{query}">{w["sign_in"]}</a>' if role == "anon" else f'<span class="muted">{w["role"]}: {w[role]}</span>'
        markup = f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">{self._style(request.theme)}<title>{escape(w["brand"])} — {escape(w[page])}</title></head><body><div class="shell"><header><div class="mast"><span class="brand">{escape(w["brand"])}</span>{account}</div><nav aria-label="{escape(w["home"])}">{nav}</nav></header><main>{content}</main><footer>{escape(w["footer"])}</footer></div></body></html>'
        return Response.html(markup)

    def _login(self, request: Request) -> Response:
        if request.method == "POST":
            values = parse_qs(request.body.decode("utf-8", "replace"))
            account = values.get("username", [""])[0]
            password = values.get("password", [""])[0]
            if (account, password) in {("owner", "owner-pass"), ("member", "member-pass")}:
                return Response.redirect(f"{request.mount}/", **{"Set-Cookie": f"session={account}; Path=/; HttpOnly"})
            error = '<p role="alert">' + self._words[request.lang]["bad_login"] + "</p>"
        else:
            error = ""
        w = self._words[request.lang]
        content = f'<p class="eyebrow">{w["sign_in"]}</p><h1>{w["login_title"]}</h1>{error}<form method="post" action="{request.mount}/login"><label>{w["username"]}<input name="username" autocomplete="username"></label><label>{w["password"]}<input name="password" type="password" autocomplete="current-password"></label><button class="tap" type="submit">{w["submit"]}</button></form>'
        return self._page(request, content, "sign_in")

    def handle(self, request: Request) -> Response:
        w = self._words[request.lang]
        role = self._role(request)
        if request.path == "/login":
            return self._login(request)
        if request.path == "/legacy":
            return Response.not_found()
        if request.path == "/":
            return self._page(request, f'<p class="eyebrow">{w["role"]}: {w[role]}</p><h1>{w["welcome"]}</h1><p>{w["intro"]}</p>{self._dashboard(w)}', "home")
        if request.path == "/users":
            if role == "anon":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{w["users"]}</p><h1>{w["users_title"]}</h1>{self._users_table(w)}{self._events(w)}', "users")
        if request.path == "/reports":
            # Intentionally backwards: a lower privilege is the only one admitted.
            if role != "member":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{w["reports"]}</p><h1>{w["reports_title"]}</h1><p>{w["note"]}</p>', "reports")
        if request.path == "/exports":
            # Intentionally hard-coded to the English route resolution.
            if request.lang != "en":
                return Response.not_found()
            if role == "anon":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{w["exports"]}</p><h1>{w["exports_title"]}</h1><p>{w["note"]}</p>', "exports")
        return Response.not_found()

    @staticmethod
    def _dashboard(w: dict[str, str]) -> str:
        detail = ("+3 this week", "2 awaiting review", "1 needs an owner") if w["brand"] == "Operations desk" else ("+3 هذا الأسبوع", "2 بانتظار المراجعة", "1 يحتاج إلى مالك")
        return f'<section class="grid"><article class="card metric"><span>{w["active"]}</span><strong>24</strong><span>{detail[0]}</span></article><article class="card metric"><span>{w["deployments"]}</span><strong>18</strong><span>{detail[1]}</span></article><article class="card metric"><span>{w["alerts"]}</span><strong>3</strong><span>{detail[2]}</span></article></section>' + AdminSite._events(w)

    @staticmethod
    def _events(w: dict[str, str]) -> str:
        events = ("Rina approved the production access review", "Atlas deployment completed successfully", "Service token rotated for billing sync") if w["brand"] == "Operations desk" else ("وافقت رينا على مراجعة وصول الإنتاج", "اكتمل إطلاق أطلس بنجاح", "تم تدوير رمز خدمة الفوترة")
        return f'<section class="events"><h2>{w["events"]}</h2><ul><li>{events[0]} · 14:20</li><li>{events[1]} · 12:48</li><li>{events[2]} · 09:15</li></ul></section>'

    @staticmethod
    def _users_table(w: dict[str, str]) -> str:
        return f'<table><thead><tr><th>{w["person"]}</th><th>{w["role"]}</th><th>{w["last_seen"]}</th><th>{w["status"]}</th></tr></thead><tbody><tr><td>Ada Mensah</td><td>{w["owner"]}</td><td>Today, 14:20</td><td>Active</td></tr><tr><td>Samira Noor</td><td>{w["member"]}</td><td>Today, 11:04</td><td>Active</td></tr><tr><td>Rina Patel</td><td>{w["member"]}</td><td>Yesterday, 16:42</td><td>Invited</td></tr></tbody></table>'
