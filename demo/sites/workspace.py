"""The Parallax shared-team workspace demo.

Seeded accounts: ``owner@demo`` (Avery, owner) and ``member@demo`` (Samira,
member).  Both accounts use the password ``demo``.  Authentication is a
session cookie issued by ``/login``.
"""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from .base import Planted, Request, Response


_STORE: dict[str, object] = {
    "accounts": {
        "owner@demo": {"role": "owner", "name": "Avery", "initials": "AK"},
        "member@demo": {"role": "member", "name": "Samira", "initials": "SK"},
    },
    "sessions": {},
    "messages": [
        {"id": 1, "thread": "general", "author": "Avery", "initials": "AK", "text": "Morning — the launch checklist is ready for a final pass.", "day": "Today", "time": "9:12 AM"},
        {"id": 2, "thread": "general", "author": "Maya Chen", "initials": "MC", "text": "I added the customer notes from yesterday’s interviews.", "day": "Today", "time": "9:28 AM"},
        {"id": 3, "thread": "general", "author": "Samira", "initials": "SK", "text": "I can take the handoff copy before lunch.", "day": "Today", "time": "10:04 AM"},
        {"id": 4, "thread": "launch", "author": "Jon Bell", "initials": "JB", "text": "Staging is green after the accessibility pass.", "day": "Yesterday", "time": "4:42 PM"},
        {"id": 5, "thread": "customer", "author": "Maya Chen", "initials": "MC", "text": "Three recurring requests are now tagged for review.", "day": "Yesterday", "time": "3:16 PM"},
        {"id": 6, "thread": "quiet", "author": "Avery", "initials": "AK", "text": "A private note kept off the shared stream.", "day": "Yesterday", "time": "1:50 PM"},
    ],
    "next_id": 7,
    "next_session": 1,
}


_COPY = {
    "en": {
        "brand": "Parallax / Fieldnotes", "title": "A clearer place to work together", "tagline": "A shared thread for decisions, handoffs, and the work that needs a home.",
        "login": "Sign in", "logout": "Sign out", "email": "Work email", "password": "Password", "welcome": "Welcome back", "bad_login": "That email or password is not valid.",
        "threads": "Threads", "settings": "Settings", "billing": "Billing", "audit": "Audit log", "overview": "Workspace overview", "team_space": "Team space", "members": "5 members", "updated": "Updated moments ago",
        "general": "General", "quiet": "Quiet", "launch": "Launch room", "customer": "Customer notes", "unread": "unread", "message": "Write a message", "send": "Send", "format": "Formatting", "attach": "Attach a file", "mention": "Mention someone",
        "today": "Today", "yesterday": "Yesterday", "all_caught_up": "You’re all caught up", "thread_list": "All conversations", "new_thread": "New thread", "activity": "Live activity", "activity_note": "Avery moved the launch checklist to Ready", "minutes": "14 min ago",
        "owner": "Owner tools", "not_allowed": "You do not have access to this page.", "signed_out": "Please sign in to continue.",
        "settings_title": "Workspace settings", "settings_lead": "Set the defaults that keep Fieldnotes useful for everyone.", "general_settings": "General", "general_desc": "Name, timezone, and the workspace identity.", "notifications": "Notifications", "notifications_desc": "Choose which shared activity reaches the team.", "permissions": "Permissions", "permissions_desc": "Control invitations and owner-only workspace access.", "workspace_name": "Workspace name", "timezone": "Timezone", "save": "Save changes", "invite": "Anyone with an invite can join", "digest": "Weekly activity digest", "member_role": "Default member role", "member": "Member",
        "billing_title": "Plan & billing", "billing_lead": "A simple view of the workspace plan and its monthly use.", "current_plan": "Current plan", "team_plan": "Team", "plan_price": "$24 / member / month", "manage_plan": "Manage plan", "usage": "Usage this month", "messages_used": "1,284 of 2,000 shared messages", "invoices": "Invoices", "invoice": "Invoice", "date": "Date", "amount": "Amount", "status": "Status", "paid": "Paid", "download": "Download PDF",
        "audit_title": "Audit log", "audit_copy": "Recent workspace access and policy changes.", "actor": "Actor", "action": "Action", "target": "Target", "timestamp": "Timestamp", "footer": "Fieldnotes for teams that keep momentum visible.", "primary_nav": "Primary navigation", "thread_options": "More thread options",
    },
    "ar": {
        "brand": "بارالاكس / ملاحظات العمل", "title": "مكان أوضح للعمل معًا", "tagline": "محادثة مشتركة للقرارات والتسليمات والعمل الذي يحتاج إلى موطن.",
        "login": "تسجيل الدخول", "logout": "تسجيل الخروج", "email": "بريد العمل", "password": "كلمة المرور", "welcome": "مرحبًا بعودتك", "bad_login": "البريد الإلكتروني أو كلمة المرور غير صحيحين.",
        "threads": "المحادثات", "settings": "الإعدادات", "billing": "الفوترة", "audit": "سجل التدقيق", "overview": "نظرة على مساحة العمل", "team_space": "مساحة الفريق", "members": "٥ أعضاء", "updated": "تم التحديث الآن",
        "general": "عام", "quiet": "هادئ", "launch": "غرفة الإطلاق", "customer": "ملاحظات العملاء", "unread": "غير مقروء", "message": "اكتب رسالة", "send": "إرسال", "format": "تنسيق", "attach": "إرفاق ملف", "mention": "إشارة إلى شخص",
        "today": "اليوم", "yesterday": "أمس", "all_caught_up": "أنت على اطلاع كامل", "thread_list": "كل المحادثات", "new_thread": "محادثة جديدة", "activity": "نشاط مباشر", "activity_note": "نقل أفيري قائمة الإطلاق إلى جاهزة", "minutes": "قبل ١٤ دقيقة",
        "owner": "أدوات المالك", "not_allowed": "ليس لديك صلاحية الوصول إلى هذه الصفحة.", "signed_out": "يرجى تسجيل الدخول للمتابعة.",
        "settings_title": "إعدادات مساحة العمل", "settings_lead": "اضبط الإعدادات التي تحافظ على فائدة ملاحظات العمل للجميع.", "general_settings": "عام", "general_desc": "الاسم والمنطقة الزمنية وهوية مساحة العمل.", "notifications": "الإشعارات", "notifications_desc": "اختر النشاط المشترك الذي يصل إلى الفريق.", "permissions": "الصلاحيات", "permissions_desc": "تحكم في الدعوات ووصول المالك فقط.", "workspace_name": "اسم مساحة العمل", "timezone": "المنطقة الزمنية", "save": "حفظ التغييرات", "invite": "يمكن لأي شخص لديه دعوة الانضمام", "digest": "ملخص النشاط الأسبوعي", "member_role": "دور العضو الافتراضي", "member": "عضو",
        "billing_title": "الخطة والفوترة", "billing_lead": "عرض بسيط لخطة مساحة العمل واستخدامها الشهري.", "current_plan": "الخطة الحالية", "team_plan": "الفريق", "plan_price": "٢٤ دولارًا / عضو / شهر", "manage_plan": "إدارة الخطة", "usage": "استخدام هذا الشهر", "messages_used": "١٬٢٨٤ من ٢٬٠٠٠ رسالة مشتركة", "invoices": "الفواتير", "invoice": "الفاتورة", "date": "التاريخ", "amount": "المبلغ", "status": "الحالة", "paid": "مدفوعة", "download": "تنزيل PDF",
        "audit_title": "سجل التدقيق", "audit_copy": "آخر عمليات الوصول إلى مساحة العمل وتغييرات السياسات.", "actor": "الفاعل", "action": "الإجراء", "target": "الهدف", "timestamp": "الوقت", "footer": "ملاحظات العمل للفرق التي تحافظ على وضوح التقدم.", "primary_nav": "التنقل الرئيسي", "thread_options": "خيارات إضافية للمحادثة",
    },
}


class WorkspaceSite:
    name = "workspace"
    title = "Parallax Fieldnotes"
    planted = [
        Planted("escalation", "privilege", "/audit", "The audit template is accidentally public."),
        Planted("rtl_not_mirrored", "locale", "/threads", "Composer controls use physical left spacing."),
        Planted("theme_layout_shift", "theme", "/threads", "Dark mode adds a header border."),
        Planted("propagation", "relational", "/threads", "Quiet-thread messages do not reach polling clients."),
    ]

    def handle(self, request: Request) -> Response:
        lang, theme = request.lang, request.theme
        if request.path == "/":
            return self._page(request, self._landing(request, lang), lang, theme, "home")
        if request.path == "/login":
            return self._login(request, lang, theme)
        if request.path == "/threads":
            user = self._user(request)
            if user is None:
                return self._login_redirect(request)
            if request.method == "POST":
                return self._post_message(request, user)
            return self._page(request, self._threads(request, lang, user), lang, theme, "threads")
        if request.path == "/api/messages":
            if self._user(request) is None:
                return Response.json({"error": "authentication required"}, status=401)
            return self._messages(request)
        if request.path in ("/settings", "/billing"):
            user = self._user(request)
            if user is None:
                return self._login_redirect(request)
            if user["role"] != "owner":
                return self._page(request, f'<main class="notice"><h1>{escape(_COPY[lang]["not_allowed"])}</h1></main>', lang, theme, "")
            content = self._settings(request, lang) if request.path == "/settings" else self._billing(request, lang)
            return self._page(request, content, lang, theme, request.path[1:])
        if request.path == "/audit":
            return self._page(request, self._audit(lang), lang, theme, "audit")
        return Response.not_found()

    @staticmethod
    def _form(request: Request) -> dict[str, str]:
        return {key: values[-1] for key, values in parse_qs(request.body.decode("utf-8", "replace")).items() if values}

    @staticmethod
    def _user(request: Request) -> dict[str, str] | None:
        email = _STORE["sessions"].get(request.cookies.get("session", ""))  # type: ignore[union-attr]
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
                number = int(_STORE["next_session"])
                token = f"workspace-{number}"
                _STORE["next_session"] = number + 1
                _STORE["sessions"][token] = form["email"]  # type: ignore[index]
                return Response.redirect(f"{request.mount}/threads", **{"Set-Cookie": f"session={token}; Path=/; HttpOnly; SameSite=Lax"})
            return self._page(request, f'<main class="auth"><p class="error">{escape(copy["bad_login"])}</p>{self._login_form(request, copy)}</main>', lang, theme, "")
        return self._page(request, f'<main class="auth">{self._login_form(request, copy)}</main>', lang, theme, "")

    @staticmethod
    def _login_form(request: Request, copy: dict[str, str]) -> str:
        return f'''<p class="kicker">{escape(copy["brand"])}</p><h1>{escape(copy["welcome"])}</h1><p>{escape(copy["tagline"])}</p><form method="post" action="{request.mount}/login"><label>{escape(copy["email"])}<input name="email" type="email" autocomplete="email" required></label><label>{escape(copy["password"])}<input name="password" type="password" autocomplete="current-password" required></label><button type="submit">{escape(copy["login"])}</button></form>'''

    def _post_message(self, request: Request, user: dict[str, str]) -> Response:
        form = self._form(request)
        text = form.get("message", "").strip()
        thread = form.get("thread", "general")
        if thread not in ("general", "quiet", "launch", "customer"):
            thread = "general"
        if text:
            message_id = int(_STORE["next_id"])
            _STORE["next_id"] = message_id + 1
            _STORE["messages"].append({"id": message_id, "thread": thread, "author": user["name"], "initials": user["initials"], "text": text, "day": "Today", "time": "just now"})  # type: ignore[union-attr]
            return Response.redirect(f"{request.mount}/threads?posted={message_id}")
        return Response.redirect(f"{request.mount}/threads")

    @staticmethod
    def _messages(request: Request) -> Response:
        try:
            since = max(0, int(request.query.get("since", "0")))
        except ValueError:
            since = 0
        messages = [item for item in _STORE["messages"] if item["id"] > since and item["thread"] != "quiet"]  # type: ignore[index]
        return Response.json({"messages": messages})

    def _landing(self, request: Request, lang: str) -> str:
        c = _COPY[lang]
        return f'''<main class="landing"><section class="hero"><div><p class="kicker">{escape(c["brand"])}</p><h1>{escape(c["title"])}</h1><p class="lead">{escape(c["tagline"])}</p><a class="button" href="{request.mount}/login">{escape(c["login"])}</a></div><aside class="activity-card"><p class="kicker">{escape(c["activity"])}</p><div class="activity-row"><span class="avatar">AK</span><div><strong>{escape(c["activity_note"])}</strong><small>{escape(c["minutes"])}</small></div></div><div class="pulse"><span></span><span></span><span></span></div><p class="quiet-copy">{escape(c["all_caught_up"])}</p></aside></section><section class="proof"><article><strong>5</strong><span>{escape(c["members"])}</span></article><article><strong>12</strong><span>{escape(c["thread_list"])}</span></article><article><strong>1,284</strong><span>{escape(c["messages_used"])}</span></article></section><section class="preview"><div><p class="kicker">{escape(c["overview"])}</p><h2>{escape(c["thread_list"])}</h2></div><div class="preview-list"><article><span class="avatar">MC</span><div><strong>{escape(c["customer"])}</strong><p>{escape(c["activity_note"])}</p></div><small>{escape(c["minutes"])}</small></article><article><span class="avatar">JB</span><div><strong>{escape(c["launch"])}</strong><p>{escape(c["updated"])}</p></div><small>4</small></article></div></section></main>'''

    def _threads(self, request: Request, lang: str, user: dict[str, str]) -> str:
        c = _COPY[lang]
        names = {"general": c["general"], "quiet": c["quiet"], "launch": c["launch"], "customer": c["customer"]}
        previews = {"general": "I can take the handoff copy before lunch.", "quiet": "A private note kept off the shared stream.", "launch": "Staging is green after the accessibility pass.", "customer": "Three recurring requests are now tagged for review."}
        items = "".join(f'<a class="thread-item {"active" if key == "general" else ""}" href="{request.mount}/threads#{key}"><span><strong>{escape(name)}</strong><small>{escape(previews[key])}</small></span>{"<b>3</b>" if key == "general" else ""}</a>' for key, name in names.items())
        message_rows = "".join(f'<article class="message"><span class="avatar">{escape(item["initials"])}</span><div><p><strong>{escape(item["author"])}</strong><time>{escape(c["today"] if item["day"] == "Today" else c["yesterday"])} · {escape(item["time"])}</time></p><span>{escape(item["text"])}</span></div></article>' for item in _STORE["messages"] if item["thread"] == "general")  # type: ignore[index]
        last_id = max(item["id"] for item in _STORE["messages"])  # type: ignore[index]
        return f'''<main class="app-shell"><aside class="thread-nav"><div class="side-heading"><div><p class="kicker">{escape(c["team_space"])}</p><h1>{escape(c["threads"])}</h1></div><a class="icon-button" href="{request.mount}/threads#new" aria-label="{escape(c["new_thread"])}">+</a></div><nav aria-label="{escape(c["thread_list"])}">{items}</nav><div class="member-card"><span class="avatar">{escape(user["initials"])}</span><div><strong>{escape(user["name"])}</strong><small>{escape(c["members"])}</small></div></div></aside><section class="thread-view"><header class="thread-header"><div><p class="kicker">{escape(c["team_space"])}</p><h1>{escape(c["general"])}</h1><p>{escape(c["members"])} · {escape(c["updated"])}</p></div><button class="more" type="button" aria-label="{escape(c["thread_options"])}">•••</button></header><div class="day-label"><span>{escape(c["today"])}</span></div><div class="messages" data-latest="{last_id}">{message_rows}</div><form class="composer" method="post" action="{request.mount}/threads"><div class="composer-tools"><button type="button" aria-label="{escape(c["format"])}">B</button><button type="button" aria-label="{escape(c["attach"])}">+</button><button type="button" aria-label="{escape(c["mention"])}">@</button><label><input type="radio" name="thread" value="general" checked>{escape(c["general"])}</label><label><input type="radio" name="thread" value="quiet">{escape(c["quiet"])}</label></div><label class="sr-only" for="message">{escape(c["message"])}</label><input id="message" name="message" type="text" placeholder="{escape(c["message"])}" required><button type="submit">{escape(c["send"])}</button></form></section></main><script>const box=document.querySelector('.messages');let latest=Number(box.dataset.latest);setInterval(async()=>{{try{{const r=await fetch('{request.mount}/api/messages?since='+latest);const d=await r.json();if(d.messages&&d.messages.length)location.reload()}}catch(e){{}}}},1000);</script>'''

    def _settings(self, request: Request, lang: str) -> str:
        c = _COPY[lang]
        group = lambda title, description, inner: f'<section class="setting-group"><div><h2>{escape(title)}</h2><p>{escape(description)}</p></div>{inner}</section>'
        return f'''<main class="admin"><p class="kicker">{escape(c["owner"])}</p><h1>{escape(c["settings_title"])}</h1><p class="lead">{escape(c["settings_lead"])}</p><form class="settings-form" method="post" action="{request.mount}/settings">{group(c["general_settings"], c["general_desc"], f'<label>{escape(c["workspace_name"])}<input type="text" value="Fieldnotes" name="workspace-name"></label><label>{escape(c["timezone"])}<select name="timezone"><option>UTC</option><option>America/New_York</option></select></label>')}{group(c["notifications"], c["notifications_desc"], f'<label class="check"><input type="checkbox" checked name="digest">{escape(c["digest"])}</label>')}{group(c["permissions"], c["permissions_desc"], f'<label class="check"><input type="checkbox" checked name="invite">{escape(c["invite"])}</label><label>{escape(c["member_role"])}<select name="role"><option>{escape(c["member"])}</option></select></label>')}<button type="submit">{escape(c["save"])}</button></form></main>'''

    def _billing(self, request: Request, lang: str) -> str:
        c = _COPY[lang]
        rows = (("INV-2026-041", "Aug 01, 2026", "$120.00"), ("INV-2026-032", "Jul 01, 2026", "$120.00"), ("INV-2026-021", "Jun 01, 2026", "$120.00"))
        table = "".join(f'<tr><td>{invoice}</td><td>{date}</td><td>{amount}</td><td><span class="status">{escape(c["paid"])}</span></td><td><a href="{request.mount}/billing#{invoice}">{escape(c["download"])}</a></td></tr>' for invoice, date, amount in rows)
        return f'''<main class="admin"><p class="kicker">{escape(c["owner"])}</p><h1>{escape(c["billing_title"])}</h1><p class="lead">{escape(c["billing_lead"])}</p><section class="billing-grid"><article class="plan"><p>{escape(c["current_plan"])}</p><h2>{escape(c["team_plan"])}</h2><strong>{escape(c["plan_price"])}</strong><a class="button secondary" href="{request.mount}/billing#plan">{escape(c["manage_plan"])}</a></article><article class="usage"><p>{escape(c["usage"])}</p><strong>64%</strong><div class="meter" role="progressbar" aria-label="{escape(c["usage"])}" aria-valuenow="64" aria-valuemin="0" aria-valuemax="100"><span></span></div><small>{escape(c["messages_used"])}</small></article></section><section class="table-card"><div><h2>{escape(c["invoices"])}</h2><p>{escape(c["current_plan"])}</p></div><div class="table-scroll"><table><thead><tr><th>{escape(c["invoice"])}</th><th>{escape(c["date"])}</th><th>{escape(c["amount"])}</th><th>{escape(c["status"])}</th><th><span class="sr-only">{escape(c["download"])}</span></th></tr></thead><tbody>{table}</tbody></table></div></section></main>'''

    def _audit(self, lang: str) -> str:
        c = _COPY[lang]
        rows = (("Avery Kim", "Changed billing owner", "Team plan", "Today, 10:18 AM"), ("Samira Khan", "Invited member", "Mira Patel", "Today, 9:44 AM"), ("Maya Chen", "Updated notification preference", "Weekly digest", "Yesterday, 4:02 PM"), ("Avery Kim", "Exported workspace data", "Fieldnotes", "Yesterday, 11:30 AM"))
        body = "".join(f'<tr><td><span class="person"><span class="avatar">{escape(actor.split()[0][0] + actor.split()[1][0])}</span>{escape(actor)}</span></td><td>{escape(action)}</td><td>{escape(target)}</td><td><time>{escape(timestamp)}</time></td></tr>' for actor, action, target, timestamp in rows)
        return f'''<main class="admin"><p class="kicker">{escape(c["owner"])}</p><h1>{escape(c["audit_title"])}</h1><p class="lead">{escape(c["audit_copy"])}</p><section class="table-card"><div><h2>{escape(c["activity"])}</h2><p>{escape(c["audit_copy"])}</p></div><div class="table-scroll"><table><thead><tr><th>{escape(c["actor"])}</th><th>{escape(c["action"])}</th><th>{escape(c["target"])}</th><th>{escape(c["timestamp"])}</th></tr></thead><tbody>{body}</tbody></table></div></section></main>'''

    def _page(self, request: Request, content: str, lang: str, theme: str, active: str) -> Response:
        c, direction = _COPY[lang], "rtl" if lang == "ar" else "ltr"
        links = (("threads", c["threads"]), ("settings", c["settings"]), ("billing", c["billing"]), ("audit", c["audit"]))
        nav = "".join(f'<a class="{"active" if key == active else ""}" href="{request.mount}/{key}">{escape(label)}</a>' for key, label in links)
        cookie = f"lang={lang}; Path=/; SameSite=Lax" if "lang" in request.query else (f"theme={theme}; Path=/; SameSite=Lax" if "theme" in request.query else "")
        header = f'<header class="site-header"><a class="brand" href="{request.mount}/">{escape(c["brand"])}</a><nav aria-label="{escape(c["primary_nav"])}">{nav}</nav><a class="login-link" href="{request.mount}/login">{escape(c["login"])}</a></header>'
        return Response.html(f'<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(c["brand"])}</title><style>{self._css(theme)}</style></head><body>{header}{content}<footer class="site-footer">{escape(c["footer"])}</footer></body></html>', **({"Set-Cookie": cookie} if cookie else {}))

    @staticmethod
    def _css(theme: str) -> str:
        palette = "--canvas:#111b22;--surface:#172630;--surface-2:#20323d;--text:#f2f6f3;--muted:#b8c7c5;--line:#38505a;--accent:#9ed84c;--accent-ink:#14210b;--danger:#ff9e92;" if theme == "dark" else "--canvas:#f5f3ed;--surface:#fffef9;--surface-2:#edf1e8;--text:#17242a;--muted:#59686b;--line:#cdd7d2;--accent:#4d7b25;--accent-ink:#fff;--danger:#af3025;"
        dark_border = ".site-header{border-block-end:3px solid var(--accent)}" if theme == "dark" else ""
        return f''' :root{{{palette}}}*{{box-sizing:border-box}}html{{background:var(--canvas)}}body{{margin:0;background:var(--canvas);color:var(--text);font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}a{{color:inherit;text-decoration:none}}button,input,select{{font:inherit}}button,a,input,select{{min-block-size:44px}}button,.button{{border:1px solid transparent;border-radius:.45rem;background:var(--accent);color:var(--accent-ink);cursor:pointer;font-weight:750;padding-block:.6rem;padding-inline:1rem}}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{{outline:3px solid var(--text);outline-offset:2px}}.site-header{{align-items:center;background:var(--surface);border-block-end:1px solid var(--line);display:flex;gap:1.25rem;justify-content:space-between;padding-block:.7rem;padding-inline:clamp(1rem,4vw,4rem)}}{dark_border}.brand,.kicker{{color:var(--accent);font-size:.75rem;font-weight:850;letter-spacing:.11em;text-transform:uppercase}}.site-header nav{{display:flex;flex-wrap:wrap;gap:.2rem}}.site-header nav a,.login-link{{align-items:center;border-radius:.35rem;color:var(--muted);display:inline-flex;padding-inline:.7rem}}.site-header nav a.active{{background:var(--surface-2);color:var(--text)}}.login-link{{border:1px solid var(--line);color:var(--text)}}main{{margin-inline:auto;max-inline-size:76rem;padding-block:clamp(2rem,5vw,4.5rem);padding-inline:clamp(1rem,4vw,4rem)}}h1,h2,p{{margin-block-start:0}}h1{{font-size:clamp(2rem,4vw,3.75rem);letter-spacing:-.045em;line-height:1.02;margin-block-end:1rem}}h2{{font-size:1.25rem;letter-spacing:-.02em}}.lead{{color:var(--muted);font-size:1.1rem;max-inline-size:56ch}}small,time{{color:var(--muted);font-size:.82rem}}.site-footer{{border-block-start:1px solid var(--line);color:var(--muted);font-size:.85rem;padding-block:1.5rem;padding-inline:clamp(1rem,4vw,4rem)}}.landing{{padding-block-start:clamp(3rem,10vh,8rem)}}.hero{{align-items:start;display:grid;gap:clamp(2rem,6vw,7rem);grid-template-columns:minmax(0,1.15fr) minmax(17rem,.85fr)}}.hero h1{{font-size:clamp(3rem,7vw,6.4rem);max-inline-size:10ch}}.activity-card,.preview,.table-card{{background:var(--surface);border:1px solid var(--line);border-radius:.7rem;padding:1.35rem}}.activity-row,.member-card,.person{{align-items:center;display:flex;gap:.7rem}}.activity-row div{{display:grid;gap:.15rem}}.avatar{{align-items:center;background:var(--accent);border-radius:50%;color:var(--accent-ink);display:inline-flex;flex:0 0 2.45rem;font-size:.72rem;font-weight:850;justify-content:center;inline-size:2.45rem;block-size:2.45rem}}.pulse{{display:flex;gap:.3rem;margin-block:2rem 1rem}}.pulse span{{background:var(--accent);block-size:.5rem;border-radius:99px;inline-size:.5rem}}.pulse span:nth-child(2){{opacity:.65}}.pulse span:nth-child(3){{opacity:.3}}.quiet-copy{{color:var(--muted);margin-block-end:0}}.proof{{display:grid;gap:1rem;grid-template-columns:repeat(3,1fr);margin-block:4rem}}.proof article{{border-block-start:2px solid var(--accent);padding-block-start:.8rem}}.proof strong{{display:block;font-size:2rem;font-variant-numeric:tabular-nums}}.proof span{{color:var(--muted)}}.preview{{align-items:start;display:grid;gap:2rem;grid-template-columns:.6fr 1fr}}.preview-list{{display:grid;gap:.3rem}}.preview-list article{{align-items:center;border-block-end:1px solid var(--line);display:grid;gap:.75rem;grid-template-columns:auto 1fr auto;padding-block:.8rem}}.preview-list article:last-child{{border:0}}.preview-list p{{color:var(--muted);font-size:.9rem;margin-block-end:0}}.auth{{max-inline-size:32rem;min-block-size:calc(100vh - 11rem)}}.auth form{{display:grid;gap:1rem;margin-block-start:2rem}}label{{display:grid;gap:.35rem;font-weight:700}}input,select{{background:var(--surface);border:1px solid var(--line);border-radius:.4rem;color:var(--text);padding-block:.65rem;padding-inline:.75rem}}.error{{color:var(--danger);font-weight:700}}.app-shell{{display:grid;gap:clamp(1.25rem,4vw,4rem);grid-template-columns:minmax(13rem,17rem) minmax(0,1fr);max-inline-size:86rem}}.thread-nav{{border-inline-end:1px solid var(--line);display:grid;gap:1.25rem;padding-inline-end:1.25rem}}.side-heading{{align-items:start;display:flex;justify-content:space-between}}.side-heading h1{{font-size:1.7rem;margin-block-end:0}}.icon-button{{align-items:center;background:var(--accent);border-radius:50%;color:var(--accent-ink);display:flex;font-size:1.4rem;font-weight:750;justify-content:center;inline-size:44px;padding:0}}.thread-nav nav{{display:grid;gap:.25rem}}.thread-item{{align-items:center;border-radius:.45rem;display:flex;gap:.5rem;justify-content:space-between;padding-block:.6rem;padding-inline:.7rem}}.thread-item.active{{background:var(--surface-2)}}.thread-item span{{display:grid;min-inline-size:0}}.thread-item small{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.thread-item b{{align-items:center;background:var(--accent);border-radius:99px;color:var(--accent-ink);display:inline-flex;font-size:.75rem;justify-content:center;min-inline-size:1.5rem;padding-inline:.3rem}}.member-card{{border-block-start:1px solid var(--line);margin-block-start:auto;padding-block-start:1rem}}.member-card div{{display:grid}}.thread-view{{min-inline-size:0}}.thread-header{{align-items:start;border-block-end:1px solid var(--line);display:flex;justify-content:space-between;padding-block-end:1.25rem}}.thread-header h1{{font-size:2.1rem;margin-block-end:.25rem}}.thread-header p{{color:var(--muted);margin-block-end:0}}.more{{background:transparent;border-color:var(--line);color:var(--text);letter-spacing:.15em}}.day-label{{align-items:center;color:var(--muted);display:flex;font-size:.8rem;gap:1rem;margin-block:1.25rem}}.day-label::before,.day-label::after{{background:var(--line);content:"";block-size:1px;flex:1}}.messages{{display:grid;gap:1rem}}.message{{display:flex;gap:.8rem;max-inline-size:46rem}}.message div{{display:grid;gap:.25rem}}.message p{{display:flex;gap:.55rem;margin-block-end:0}}.message time{{font-variant-numeric:tabular-nums}}.composer{{border-block-start:1px solid var(--line);display:grid;gap:.7rem;grid-template-columns:minmax(0,1fr) auto;margin-block-start:2rem;padding-block-start:3.5rem;position:relative}}.composer-tools{{align-items:center;display:flex;gap:.35rem;inset-block-start:.45rem;left:.75rem;margin-left:.25rem;position:absolute}}.composer-tools button{{background:transparent;border:0;color:var(--muted);min-block-size:34px;min-inline-size:34px;padding:0}}.composer-tools label{{align-items:center;color:var(--muted);display:flex;font-size:.78rem;font-weight:650;gap:.25rem}}.composer-tools input{{block-size:1rem;inline-size:1rem;min-block-size:1rem}}.sr-only{{block-size:1px;clip:rect(0,0,0,0);inline-size:1px;margin:-1px;overflow:hidden;position:absolute;white-space:nowrap}}.admin{{max-inline-size:72rem}}.settings-form{{display:grid;gap:1rem;margin-block-start:2.5rem}}.setting-group{{background:var(--surface);border:1px solid var(--line);border-radius:.65rem;display:grid;gap:1.5rem;grid-template-columns:minmax(12rem,.7fr) minmax(0,1fr);padding:1.25rem}}.setting-group p{{color:var(--muted);margin-block-end:0}}.setting-group label{{margin-block-end:.8rem}}.check{{align-items:center;display:flex;gap:.6rem}}.check input{{inline-size:1.1rem;min-block-size:1.1rem}}.billing-grid{{display:grid;gap:1rem;grid-template-columns:repeat(2,1fr);margin-block:2.5rem}}.plan,.usage{{background:var(--surface);border:1px solid var(--line);border-radius:.65rem;display:grid;gap:.75rem;padding:1.25rem}}.plan p,.usage p{{color:var(--muted);margin-block-end:0}}.plan strong,.usage strong{{font-size:1.35rem;font-variant-numeric:tabular-nums}}.secondary{{background:transparent;border-color:var(--line);color:var(--text);justify-self:start}}.meter{{background:var(--surface-2);block-size:.75rem;border-radius:99px;overflow:hidden}}.meter span{{background:var(--accent);block-size:100%;display:block;inline-size:64%}}.table-card{{margin-block-start:2rem}}.table-card > div:first-child{{align-items:baseline;display:flex;justify-content:space-between}}.table-card p{{color:var(--muted)}}.table-scroll{{overflow-x:auto}}table{{border-collapse:collapse;font-variant-numeric:tabular-nums;inline-size:100%;min-inline-size:38rem;text-align:start}}th,td{{border-block-start:1px solid var(--line);padding-block:.9rem;padding-inline:.7rem}}th{{color:var(--muted);font-size:.78rem;letter-spacing:.06em;text-transform:uppercase}}td a{{color:var(--accent);font-weight:750}}.status{{background:var(--surface-2);border-radius:99px;color:var(--text);font-size:.78rem;padding-block:.25rem;padding-inline:.55rem}}@media(max-width:48rem){{.site-header{{align-items:flex-start;flex-wrap:wrap}}.site-header nav{{order:3;inline-size:100%}}.hero,.preview,.app-shell,.setting-group{{grid-template-columns:1fr}}.proof{{margin-block:2.5rem}}.thread-nav{{border-block-end:1px solid var(--line);border-inline-end:0;padding-block-end:1rem;padding-inline-end:0}}.thread-nav nav{{grid-auto-columns:minmax(12rem,1fr);grid-auto-flow:column;overflow-x:auto}}.member-card{{display:none}}.billing-grid{{grid-template-columns:1fr}}}}@media(max-width:26rem){{.proof{{grid-template-columns:1fr}}.composer{{grid-template-columns:1fr}}.composer button[type="submit"]{{inline-size:100%}}}}'''
