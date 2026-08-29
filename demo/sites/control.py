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
        "en": {"brand": "Team ledger", "home": "Overview", "team": "Team", "reports": "Reports", "sign_in": "Sign in", "home_title": "Work, held in balance.", "home_text": "A clear record for the people doing the work.", "team_title": "The team", "reports_title": "Owner reports", "username": "Username", "password": "Password", "continue": "Continue", "login_title": "Sign in to the ledger", "wrong": "Those details are not recognised.", "role": "Current role", "owner": "Owner", "member": "Member", "anon": "Guest", "report_text": "Private operational summaries for account owners."},
        "ar": {"brand": "سجل الفريق", "home": "نظرة عامة", "team": "الفريق", "reports": "التقارير", "sign_in": "تسجيل الدخول", "home_title": "العمل في توازن واضح.", "home_text": "سجل واضح للأشخاص الذين ينجزون العمل.", "team_title": "الفريق", "reports_title": "تقارير المالك", "username": "اسم المستخدم", "password": "كلمة المرور", "continue": "متابعة", "login_title": "تسجيل الدخول إلى السجل", "wrong": "هذه البيانات غير معروفة.", "role": "الدور الحالي", "owner": "المالك", "member": "عضو", "anon": "زائر", "report_text": "ملخصات تشغيلية خاصة لمالكي الحساب."},
    }

    def _role(self, request: Request) -> str:
        session = request.cookies.get("session")
        return session if session in ("owner", "member") else "anon"

    def _css(self, theme: str) -> str:
        palette = ("#fffdf8", "#172332", "#e8eef3", "#0b5d7a", "#ffffff", "#526271", "#cbd7df") if theme == "light" else ("#121b25", "#f3f7fb", "#1d2b38", "#6ed5f5", "#192632", "#c1ced8", "#405464")
        return f"""<style>:root{{--bg:{palette[0]};--ink:{palette[1]};--wash:{palette[2]};--accent:{palette[3]};--card:{palette[4]};--muted:{palette[5]};--line:{palette[6]}}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Georgia,'Noto Naskh Arabic',serif;line-height:1.5}}.shell{{max-inline-size:1120px;margin-inline:auto;padding:clamp(16px,4vw,52px)}}header{{border-block-end:1px solid var(--line);padding-block-end:18px}}.mast{{display:flex;align-items:center;justify-content:space-between;gap:16px}}.brand{{font-size:1.12rem;font-weight:bold;letter-spacing:.04em}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin-block-start:18px}}a,.tap{{color:inherit}}.tap{{display:inline-flex;align-items:center;justify-content:center;min-block-size:44px;padding-inline:15px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:transparent;font:inherit}}.tap:hover,.tap:focus-visible{{background:var(--wash);outline:3px solid var(--accent);outline-offset:2px}}main{{padding-block:clamp(34px,7vw,86px)}}.eyebrow{{color:var(--accent);font-weight:bold;text-transform:uppercase;letter-spacing:.1em}}h1{{font-size:clamp(2.2rem,8vw,5.5rem);line-height:.95;max-inline-size:12ch;margin:12px 0}}p{{max-inline-size:62ch}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:16px;margin-block-start:34px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;min-inline-size:0}}label{{display:grid;gap:7px;font-weight:bold}}input{{min-block-size:44px;inline-size:100%;border:1px solid var(--line);border-radius:8px;padding-inline:12px;font:inherit;background:var(--card);color:var(--ink)}}form{{display:grid;gap:18px;max-inline-size:420px}}button{{cursor:pointer}}.muted{{color:var(--muted)}}@media (max-width:420px){{.shell{{padding:16px}}.mast{{align-items:flex-start;flex-direction:column}}}}</style>"""

    def _page(self, request: Request, body: str, label: str) -> Response:
        lang, words, role = request.lang, self._copy[request.lang], self._role(request)
        query = f"?lang={lang}&theme={request.theme}"
        nav = "".join(f'<a class="tap" href="{request.mount}{path}{query}">{words[key]}</a>' for path, key in (("/", "home"), ("/team", "team"), ("/reports", "reports")))
        account = f'<a class="tap" href="{request.mount}/login{query}">{words["sign_in"]}</a>' if role == "anon" else f'<span class="muted">{words["role"]}: {words[role]}</span>'
        return Response.html(f'<!doctype html><html lang="{lang}" dir="{"rtl" if lang == "ar" else "ltr"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">{self._css(request.theme)}<title>{escape(words["brand"])} — {escape(words[label])}</title></head><body><div class="shell"><header><div class="mast"><span class="brand">{escape(words["brand"])}</span>{account}</div><nav aria-label="{escape(words["home"])}">{nav}</nav></header><main>{body}</main></div></body></html>')

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
            return self._page(request, f'<p class="eyebrow">{words["role"]}: {words[role]}</p><h1>{words["home_title"]}</h1><p>{words["home_text"]}</p>', "home")
        if request.path == "/team":
            if role == "anon":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{words["team"]}</p><h1>{words["team_title"]}</h1><div class="grid"><article class="card">Mina — {words["owner"]}</article><article class="card">Noor — {words["member"]}</article></div>', "team")
        if request.path == "/reports":
            if role != "owner":
                return Response.redirect(f"{request.mount}/login")
            return self._page(request, f'<p class="eyebrow">{words["reports"]}</p><h1>{words["reports_title"]}</h1><p>{words["report_text"]}</p>', "reports")
        return Response.not_found()
