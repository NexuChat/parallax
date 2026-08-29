"""An independently implemented, correct comparison site for Parallax demos."""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from .base import Request, Response


class ControlSite:
    name = "control"
    title = "Team ledger"
    planted: list = []
    tap_targets = (".tap",)

    _copy = {
        "en": {"brand": "Team ledger", "home": "Overview", "team": "Team", "reports": "Reports", "sign_in": "Sign in", "home_title": "Work, held in balance.", "home_text": "A clear record for the people doing the work.", "team_title": "The team", "reports_title": "Owner reports", "username": "Username", "password": "Password", "continue": "Continue", "login_title": "Sign in to the ledger", "wrong": "Those details are not recognised.", "role": "Current role", "owner": "Owner", "member": "Member", "anon": "Guest", "report_text": "Private operational summaries for account owners.", "active":"Active seats","deployments":"Deployments today","alerts":"Open alerts","events":"Recent events","person":"Person","last_seen":"Last seen","status":"Status","footer":"Team ledger · A clear record for the work in motion."},
        "ar": {"brand": "سجل الفريق", "home": "نظرة عامة", "team": "الفريق", "reports": "التقارير", "sign_in": "تسجيل الدخول", "home_title": "العمل في توازن واضح.", "home_text": "سجل واضح للأشخاص الذين ينجزون العمل.", "team_title": "الفريق", "reports_title": "تقارير المالك", "username": "اسم المستخدم", "password": "كلمة المرور", "continue": "متابعة", "login_title": "تسجيل الدخول إلى السجل", "wrong": "هذه البيانات غير معروفة.", "role": "الدور الحالي", "owner": "المالك", "member": "عضو", "anon": "زائر", "report_text": "ملخصات تشغيلية خاصة لمالكي الحساب.", "active":"المقاعد النشطة","deployments":"إطلاقات اليوم","alerts":"تنبيهات مفتوحة","events":"الأحداث الأخيرة","person":"الشخص","last_seen":"آخر ظهور","status":"الحالة","footer":"سجل الفريق · سجل واضح للعمل الجاري."},
    }

    def _role(self, request: Request) -> str:
        session = request.cookies.get("session")
        return session if session in ("owner", "member") else "anon"

    def _css(self, theme: str) -> str:
        palette = ("#fffdf8", "#172332", "#e8eef3", "#0b5d7a", "#ffffff", "#526271", "#cbd7df") if theme == "light" else ("#121b25", "#f3f7fb", "#1d2b38", "#6ed5f5", "#192632", "#c1ced8", "#405464")
        return f"""<style>:root{{--bg:{palette[0]};--ink:{palette[1]};--wash:{palette[2]};--accent:{palette[3]};--card:{palette[4]};--muted:{palette[5]};--line:{palette[6]}}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Georgia,'Noto Naskh Arabic',serif;line-height:1.5;overflow-x:hidden}}.shell{{max-inline-size:1120px;margin-inline:auto;padding:clamp(16px,4vw,52px)}}header{{border-block-end:1px solid var(--line);padding-block-end:18px}}footer{{border-block-start:1px solid var(--line);padding-block:24px;color:var(--muted);font-size:.9rem}}.mast{{display:flex;align-items:center;justify-content:space-between;gap:16px}}.brand{{font-size:1.12rem;font-weight:bold;letter-spacing:.04em}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin-block-start:18px}}a,.tap{{color:inherit}}.tap{{display:inline-flex;align-items:center;justify-content:center;min-block-size:44px;padding-inline:15px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:transparent;font:inherit}}.tap:hover,.tap:focus-visible{{background:var(--wash);outline:3px solid var(--accent);outline-offset:2px}}main{{padding-block:clamp(34px,6vw,66px)}}.eyebrow{{color:var(--accent);font-weight:bold;text-transform:uppercase;letter-spacing:.1em}}h1{{font-size:clamp(2.2rem,6vw,4.4rem);line-height:.95;max-inline-size:15ch;margin:12px 0}}p{{max-inline-size:62ch}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:16px;margin-block-start:28px}}.card,.events,table{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;min-inline-size:0}}.metric strong{{display:block;font:700 2rem/1 system-ui,sans-serif;margin-block:8px}}.metric span,.muted{{color:var(--muted)}}.events{{margin-block-start:28px}}.events ul{{margin:0;padding-inline-start:20px}}.events li{{padding-block:8px;border-block-end:1px solid var(--line)}}.events li:last-child{{border:0}}table{{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;padding:0;overflow:hidden;margin-block-start:28px;font-variant-numeric:tabular-nums}}th,td{{padding:14px;text-align:start;border-block-end:1px solid var(--line);overflow-wrap:anywhere}}tr:last-child td{{border:0}}th{{font:700 .78rem/1 system-ui,sans-serif;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}}label{{display:grid;gap:7px;font-weight:bold}}input{{min-block-size:44px;inline-size:100%;border:1px solid var(--line);border-radius:8px;padding-inline:12px;font:inherit;background:var(--card);color:var(--ink)}}form{{display:grid;gap:18px;max-inline-size:420px}}button{{cursor:pointer}}@media (max-width:420px){{.shell{{padding:16px}}.mast{{align-items:flex-start;flex-direction:column}}table{{font-size:.85rem}}th,td{{padding:10px 7px}}}}</style>"""

    def _page(self, request: Request, body: str, label: str) -> Response:
        lang, words, role = request.lang, self._copy[request.lang], self._role(request)
        query = f"?lang={lang}&theme={request.theme}"
        nav = "".join(f'<a class="tap" href="{request.mount}{path}{query}">{words[key]}</a>' for path, key in (("/", "home"), ("/team", "team"), ("/reports", "reports")))
        account = f'<a class="tap" href="{request.mount}/login{query}">{words["sign_in"]}</a>' if role == "anon" else f'<span class="muted">{words["role"]}: {words[role]}</span>'
        return Response.html(f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">{self._css(request.theme)}<title>{escape(words["brand"])} — {escape(words[label])}</title></head><body><div class="shell"><header><div class="mast"><span class="brand">{escape(words["brand"])}</span>{account}</div><nav aria-label="{escape(words["home"])}">{nav}</nav></header><main>{body}</main><footer>{escape(words["footer"])}</footer></div></body></html>')

    def _login(self, request: Request) -> Response:
        words = self._copy[request.lang]
        notice = ""
        if request.method == "POST":
            form = parse_qs(request.body.decode("utf-8", "replace"))
            username, password = form.get("username", [""])[0], form.get("password", [""])[0]
            if (username, password) in (("owner", "owner-pass"), ("member", "member-pass")):
                return Response.redirect(f"{request.mount}/", **{"Set-Cookie": f"session={username}; Path=/; HttpOnly"})
            notice = f'<p role="alert">{words["wrong"]}</p>'
        return self._page(request, f'<p class="eyebrow">{words["sign_in"]}</p><h1>{words["login_title"]}</h1>{notice}<form method="post" action="{request.mount}/login"><label>{words["username"]}<input name="username" autocomplete="username"></label><label>{words["password"]}<input name="password" type="password" autocomplete="current-password"></label><button class="tap" type="submit">{words["continue"]}</button></form>', "sign_in")

    def handle(self, request: Request) -> Response:
        words, role = self._copy[request.lang], self._role(request)
        if request.path == "/login":
            return self._login(request)
        if request.path == "/":
            return self._page(request, f'<p class="eyebrow">{words["role"]}: {words[role]}</p><h1>{words["home_title"]}</h1><p>{words["home_text"]}</p>{self._dashboard(words)}', "home")
        if request.path == "/team":
            if role == "anon":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{words["team"]}</p><h1>{words["team_title"]}</h1>{self._team_table(words)}{self._events(words)}', "team")
        if request.path == "/reports":
            if role != "owner":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{words["reports"]}</p><h1>{words["reports_title"]}</h1><p>{words["report_text"]}</p>', "reports")
        return Response.not_found()

    @staticmethod
    def _dashboard(w: dict[str, str]) -> str:
        detail = ("+3 this week", "2 awaiting review", "Everything is healthy") if w["brand"] == "Team ledger" else ("+3 هذا الأسبوع", "2 بانتظار المراجعة", "كل شيء يعمل")
        return f'<section class="grid"><article class="card metric"><span>{w["active"]}</span><strong>24</strong><span>{detail[0]}</span></article><article class="card metric"><span>{w["deployments"]}</span><strong>18</strong><span>{detail[1]}</span></article><article class="card metric"><span>{w["alerts"]}</span><strong>0</strong><span>{detail[2]}</span></article></section>' + ControlSite._events(w)

    @staticmethod
    def _events(w: dict[str, str]) -> str:
        events = ("Production access review completed", "Atlas deployment completed successfully", "Billing service token rotated") if w["brand"] == "Team ledger" else ("تمت مراجعة الوصول إلى الإنتاج", "اكتمل إطلاق أطلس بنجاح", "تم تدوير رمز خدمة الفوترة")
        return f'<section class="events"><h2>{w["events"]}</h2><ul><li>{events[0]} · 14:20</li><li>{events[1]} · 12:48</li><li>{events[2]} · 09:15</li></ul></section>'

    @staticmethod
    def _team_table(w: dict[str, str]) -> str:
        rows = ("Mina Khalid", "Noor Halim", "Layan Omar", "Today, 14:20", "Today, 11:04", "Yesterday, 16:42", "Active", "Invited") if w["brand"] == "Team ledger" else ("مينا خالد", "نور حليم", "ليان عمر", "اليوم، 14:20", "اليوم، 11:04", "أمس، 16:42", "نشط", "مدعو")
        return f'<table><thead><tr><th>{w["person"]}</th><th>{w["role"]}</th><th>{w["last_seen"]}</th><th>{w["status"]}</th></tr></thead><tbody><tr><td>{rows[0]}</td><td>{w["owner"]}</td><td>{rows[3]}</td><td>{rows[6]}</td></tr><tr><td>{rows[1]}</td><td>{w["member"]}</td><td>{rows[4]}</td><td>{rows[6]}</td></tr><tr><td>{rows[2]}</td><td>{w["member"]}</td><td>{rows[5]}</td><td>{rows[7]}</td></tr></tbody></table>'
