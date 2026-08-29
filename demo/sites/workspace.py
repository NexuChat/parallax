"""A small shared team workspace demo.

Demo accounts are ``owner@demo`` and ``member@demo``; both use the trivial
password ``demo``.  The module is deliberately self-contained so its handler
can be called directly without a server.
"""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from .base import Planted, Request, Response


_STORE: dict[str, object] = {
    "accounts": {
        "owner@demo": {"role": "owner", "name": "Avery"},
        "member@demo": {"role": "member", "name": "Samira"},
    },
    "sessions": {},
    "messages": [
        {"id": 1, "thread": "general", "author": "Avery", "text": "Welcome to the workspace."},
    ],
    "next_id": 2,
    "next_session": 1,
}


_COPY = {
    "en": {
        "title": "Small team workspace", "tagline": "A calm home for the work your team shares.",
        "login": "Sign in", "email": "Email", "password": "Password", "welcome": "Welcome back",
        "threads": "Threads", "general": "General", "quiet": "Quiet", "message": "Write a message",
        "send": "Send", "settings": "Settings", "billing": "Billing", "audit": "Audit log",
        "owner": "Owner tools", "signed_out": "Please sign in to continue.", "bad_login": "That email or password is not valid.",
        "audit_copy": "Recent workspace access and policy changes.", "not_allowed": "You do not have access to this page.",
    },
    "ar": {
        "title": "مساحة عمل الفريق", "tagline": "منزل هادئ للعمل الذي يشاركه فريقك.",
        "login": "تسجيل الدخول", "email": "البريد الإلكتروني", "password": "كلمة المرور", "welcome": "مرحبًا بعودتك",
        "threads": "المحادثات", "general": "عام", "quiet": "هادئ", "message": "اكتب رسالة",
        "send": "إرسال", "settings": "الإعدادات", "billing": "الفوترة", "audit": "سجل التدقيق",
        "owner": "أدوات المالك", "signed_out": "يرجى تسجيل الدخول للمتابعة.", "bad_login": "البريد الإلكتروني أو كلمة المرور غير صحيحين.",
        "audit_copy": "آخر عمليات الوصول إلى مساحة العمل وتغييرات السياسات.", "not_allowed": "ليس لديك صلاحية الوصول إلى هذه الصفحة.",
    },
}


class WorkspaceSite:
    name = "workspace"
    title = "Small team workspace"
    planted = [
        Planted("escalation", "privilege", "/audit", "The audit template is accidentally public."),
        Planted("rtl_not_mirrored", "locale", "/threads", "Composer controls use physical left spacing."),
        Planted("theme_layout_shift", "theme", "/threads", "Dark mode adds a header border."),
        Planted("propagation", "relational", "/threads", "Quiet-thread messages do not reach polling clients."),
    ]

    def handle(self, request: Request) -> Response:
        lang, theme = request.lang, request.theme
        if request.path == "/":
            return self._page(request, self._landing(request, lang), lang, theme)
        if request.path == "/login":
            return self._login(request, lang, theme)
        if request.path == "/threads":
            user = self._user(request)
            if user is None:
                return self._login_redirect(request)
            if request.method == "POST":
                return self._post_message(request, user)
            return self._page(request, self._threads(request, lang, user), lang, theme)
        if request.path == "/api/messages":
            user = self._user(request)
            if user is None:
                return Response.json({"error": "authentication required"}, status=401)
            return self._messages(request)
        if request.path in ("/settings", "/billing"):
            user = self._user(request)
            if user is None:
                return self._login_redirect(request)
            if user["role"] != "owner":
                return self._page(request, f"<h1>{escape(_COPY[lang]['not_allowed'])}</h1>", lang, theme, status=403)
            label = _COPY[lang][request.path[1:]]
            return self._page(request, f"<h1>{escape(label)}</h1><p>{escape(_COPY[lang]['owner'])}</p>", lang, theme)
        if request.path == "/audit":
            # Deliberately planted: unlike the other owner pages, this template has no role gate.
            return self._page(request, self._audit(lang), lang, theme)
        return Response.not_found()

    @staticmethod
    def _form(request: Request) -> dict[str, str]:
        return {key: values[-1] for key, values in parse_qs(request.body.decode("utf-8", "replace")).items() if values}

    @staticmethod
    def _user(request: Request) -> dict[str, str] | None:
        token = request.cookies.get("session", "")
        email = _STORE["sessions"].get(token)  # type: ignore[union-attr]
        return _STORE["accounts"].get(email) if email else None  # type: ignore[union-attr,return-value]

    @staticmethod
    def _login_redirect(request: Request) -> Response:
        return Response.redirect(f"{request.mount}/login")

    def _login(self, request: Request, lang: str, theme: str) -> Response:
        copy = _COPY[lang]
        if request.method == "POST":
            form = self._form(request)
            account = _STORE["accounts"].get(form.get("email"))  # type: ignore[union-attr]
            if account and form.get("password") == "demo":
                session_number = _STORE["next_session"]  # type: ignore[assignment]
                token = f"workspace-{session_number}"
                _STORE["next_session"] = int(session_number) + 1
                _STORE["sessions"][token] = form["email"]  # type: ignore[index]
                return Response.redirect(f"{request.mount}/threads", **{"Set-Cookie": f"session={token}; Path=/; HttpOnly; SameSite=Lax"})
            content = f'<p class="error">{escape(copy["bad_login"])}</p>'
            return self._page(request, content + self._login_form(request, copy), lang, theme, status=401)
        return self._page(request, self._login_form(request, copy), lang, theme)

    @staticmethod
    def _login_form(request: Request, copy: dict[str, str]) -> str:
        return (
            f'<main class="auth"><h1>{escape(copy["welcome"])}</h1>'
            f'<form method="post" action="{request.mount}/login"><label>{escape(copy["email"])}<input name="email" type="email" required></label>'
            f'<label>{escape(copy["password"])}<input name="password" type="password" required></label>'
            f'<button type="submit">{escape(copy["login"])}</button></form></main>'
        )

    def _post_message(self, request: Request, user: dict[str, str]) -> Response:
        form = self._form(request)
        text = form.get("message", "").strip()
        thread = form.get("thread", "general")
        if thread not in ("general", "quiet"):
            thread = "general"
        if text:
            message_id = int(_STORE["next_id"])
            _STORE["next_id"] = message_id + 1
            _STORE["messages"].append({"id": message_id, "thread": thread, "author": user["name"], "text": text})  # type: ignore[union-attr]
            return Response.redirect(f"{request.mount}/threads?posted={message_id}")
        return Response.redirect(f"{request.mount}/threads")

    @staticmethod
    def _messages(request: Request) -> Response:
        try:
            since = max(0, int(request.query.get("since", "0")))
        except ValueError:
            since = 0
        # Deliberately planted: quiet messages are persisted but not broadcast to polling peers.
        messages = [message for message in _STORE["messages"] if message["id"] > since and message["thread"] != "quiet"]  # type: ignore[index]
        return Response.json({"messages": messages})

    def _landing(self, request: Request, lang: str) -> str:
        copy = _COPY[lang]
        labels = ("Recent activity", "Thread previews", "Members", "Open threads", "Files shared", "© 2026 Parallax Workspace", "Avery moved the launch checklist to Ready · 14 minutes ago", "Design review", "Maya shared three notes from the customer call.", "Release planning", "Samira confirmed the Friday handoff.") if lang == "en" else ("النشاط الأخير", "معاينات المحادثات", "الأعضاء", "المحادثات المفتوحة", "الملفات المشتركة", "© 2026 مساحة عمل بارالاكس", "نقل أفيري قائمة الإطلاق إلى جاهزة · قبل 14 دقيقة", "مراجعة التصميم", "شاركت مايا ثلاث ملاحظات من مكالمة العملاء.", "تخطيط الإطلاق", "أكدت سميرة تسليم يوم الجمعة.")
        return (
            f'<main class="landing"><section><p class="eyebrow">Parallax</p><h1>{escape(copy["title"])}</h1><p>{escape(copy["tagline"])}</p><a class="button" href="{request.mount}/login">{escape(copy["login"])}</a></section>'
            f'<section class="stats"><article><strong>18</strong><span>{labels[2]}</span></article><article><strong>6</strong><span>{labels[3]}</span></article><article><strong>42</strong><span>{labels[4]}</span></article></section><section class="activity"><p class="eyebrow">{labels[0]}</p><h2>{labels[6]}</h2><p class="eyebrow">{labels[1]}</p><div class="previews"><article><span class="avatar">M</span><div><strong>{labels[7]}</strong><p>{labels[8]}</p><small>Today, 10:42</small></div></article><article><span class="avatar">S</span><div><strong>{labels[9]}</strong><p>{labels[10]}</p><small>Yesterday, 16:20</small></div></article></div></section><footer>{labels[5]}</footer></main>'
        )

    def _threads(self, request: Request, lang: str, user: dict[str, str]) -> str:
        copy = _COPY[lang]
        rows = "".join(
            f'<article class="message"><span class="avatar">{escape(message["author"][0])}</span><div><strong>{escape(message["author"])}</strong><small>Today, 10:2{message["id"]}</small><span>{escape(message["text"])}</span></div></article>'
            for message in _STORE["messages"]  # type: ignore[union-attr]
        )
        return (
            '<main class="workspace"><aside><h2>' + escape(copy["threads"]) + "</h2>"
            f'<a href="{request.mount}/threads#general">{escape(copy["general"])} <small>8</small></a><a href="{request.mount}/threads#quiet">{escape(copy["quiet"])} <small>2</small></a><a href="{request.mount}/threads#launch">Launch room</a><a href="{request.mount}/threads#customer">Customer notes</a></aside>'
            f'<section><p class="eyebrow">Team space</p><h1>{escape(copy["general"])}</h1><p class="muted">8 participants · Updated moments ago</p><div class="messages">{rows}</div>'
            f'<form class="composer" method="post" action="{request.mount}/threads"><div class="composer-tools"><label><input type="radio" name="thread" value="general" checked>'
            f'{escape(copy["general"])}</label><label><input type="radio" name="thread" value="quiet">{escape(copy["quiet"])}</label></div>'
            f'<label class="sr-only">{escape(copy["message"])}<input name="message" type="text" required></label><button type="submit">{escape(copy["send"])}</button></form>'
            "</section></main>"
        )

    @staticmethod
    def _audit(lang: str) -> str:
        copy = _COPY[lang]
        return f"<main><h1>{escape(copy['audit'])}</h1><p>{escape(copy['audit_copy'])}</p><ul><li>Policy updated</li><li>Member invited</li></ul></main>"

    def _page(self, request: Request, content: str, lang: str, theme: str, status: int = 200) -> Response:
        copy = _COPY[lang]
        direction = "rtl" if lang == "ar" else "ltr"
        theme_cookie = ""
        if "lang" in request.query:
            theme_cookie = f"lang={lang}; Path=/; SameSite=Lax"
        elif "theme" in request.query:
            theme_cookie = f"theme={theme}; Path=/; SameSite=Lax"
        header = (
            f'<header><a href="{request.mount}/">{escape(copy["title"])}</a><nav><a href="{request.mount}/threads">{escape(copy["threads"])}</a>'
            f'<a href="{request.mount}/settings">{escape(copy["settings"])}</a><a href="{request.mount}/billing">{escape(copy["billing"])}</a></nav></header>'
        )
        return Response.html(
            f'<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(self.title)}</title><style>{self._css(theme)}</style></head><body>{header}{content}</body></html>",
            status=status,
            **({"Set-Cookie": theme_cookie} if theme_cookie else {}),
        )

    @staticmethod
    def _css(theme: str) -> str:
        colors = "--bg:#101721;--panel:#182332;--text:#edf4fb;--muted:#b7c4d2;--line:#33465a;--accent:#75d7a5;" if theme == "dark" else "--bg:#f6f8fb;--panel:#fff;--text:#15202b;--muted:#536273;--line:#d8e0e8;--accent:#087f5b;"
        dark_header = "header{border-block-end:3px solid #75d7a5;}" if theme == "dark" else ""
        return (
            f":root{{{colors}}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif}}"
            "header{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-block:1rem;padding-inline:clamp(1rem,5vw,5rem);background:var(--panel)}"
            + dark_header
            + "a{color:inherit;text-decoration:none}nav{display:flex;flex-wrap:wrap;gap:1rem;color:var(--muted)}main{max-inline-size:70rem;margin-inline:auto;padding-block:2rem;padding-inline:clamp(1rem,5vw,5rem)}"
            ".landing{padding-block:clamp(3rem,8vh,6rem)}.landing h1{max-inline-size:12ch;font-size:clamp(2.5rem,7vw,5rem);line-height:1.02}.eyebrow{color:var(--accent);font-weight:700}.muted,small{color:var(--muted)}.button,button{display:inline-block;border:0;border-radius:.5rem;background:var(--accent);color:#062116;padding-block:.7rem;padding-inline:1rem;font:inherit;font-weight:700;cursor:pointer}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-block:3rem}.stats article,.activity,.previews article{background:var(--panel);border:1px solid var(--line);border-radius:.6rem;padding:1rem}.stats strong{display:block;font-size:1.8rem}.stats span{color:var(--muted)}.activity{padding:1.5rem}.previews{display:grid;gap:.75rem}.previews article{display:flex;gap:.75rem}.previews p{margin:.15rem 0}.avatar{display:inline-grid;place-items:center;flex:0 0 2.25rem;inline-size:2.25rem;block-size:2.25rem;border-radius:50%;background:var(--accent);color:#062116;font-weight:800}footer{margin-block-start:3rem;padding-block:1.5rem;border-block-start:1px solid var(--line);color:var(--muted)}"
            ".auth{max-inline-size:28rem}.auth form{display:grid;gap:1rem}.auth label{display:grid;gap:.35rem}input{inline-size:100%;border:1px solid var(--line);border-radius:.4rem;background:var(--panel);color:var(--text);padding-block:.7rem;padding-inline:.8rem}.error{color:#c92a2a}.workspace{display:grid;grid-template-columns:minmax(10rem,14rem) minmax(0,1fr);gap:2rem}.workspace aside{display:grid;align-content:start;gap:.75rem}.workspace section{min-inline-size:0}.messages{display:grid;gap:.75rem;margin-block:1rem}.message{display:flex;gap:.75rem;background:var(--panel);border:1px solid var(--line);border-radius:.6rem;padding-block:.8rem;padding-inline:1rem}.message div{display:grid;gap:.2rem}.message strong{color:var(--accent)}"
            ".composer{position:relative;display:grid;grid-template-columns:1fr auto;gap:.75rem;padding-block-start:3rem}.composer-tools{position:absolute;left:.75rem;margin-left:.25rem;inset-block-start:.4rem;display:flex;gap:.75rem;font-size:.85rem;color:var(--muted)}.composer-tools input{inline-size:auto}.sr-only{position:absolute;inline-size:1px;block-size:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}@media (max-width:42rem){header{align-items:flex-start;flex-direction:column}.workspace{grid-template-columns:1fr}.workspace aside{grid-auto-flow:column;justify-content:start}.composer{grid-template-columns:1fr}.stats{grid-template-columns:1fr}}"
        )
