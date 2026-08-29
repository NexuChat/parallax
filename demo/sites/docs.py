"""A compact documentation site with precisely scoped comparison defects."""

from __future__ import annotations

from .base import Planted, Request, Response


_T = {
    "en": {"brand":"Northstar Docs","home":"Overview","guide":"Guide","api":"API","faq":"FAQ","eyebrow":"Reference library","headline":"Make the next release predictable.","lead":"Northstar gives small teams a clear, observable path from idea to production.","help":"Need a hand? Start with the guide or ask your workspace owner.","guide_title":"A practical guide","guide_lead":"Set up your first project, then establish the boundaries that keep it healthy.","limits":"Limits and safeguards","limits_text":"Rate limits protect the shared service and make capacity easy to reason about.","api_title":"API reference","api_text":"Every request uses JSON and a versioned endpoint.","faq_title":"Frequently asked questions","faq_text":"Short answers to the questions that arrive first.","related":"Related questions","related_text":"How do I rotate a token? · Where can I see usage?","read":"Read guide"},
    "ar": {"brand":"توثيق نورث ستار","home":"نظرة عامة","guide":"الدليل","api":"واجهة البرمجة","faq":"الأسئلة الشائعة","eyebrow":"مكتبة مرجعية","headline":"اجعل الإصدار القادم متوقعًا.","lead":"يمنح نورث ستار الفرق الصغيرة مسارًا واضحًا ومرئيًا من الفكرة إلى الإنتاج.","help":"هل تحتاج إلى مساعدة؟ ابدأ بالدليل أو اسأل مسؤول مساحة العمل.","guide_title":"دليل عملي","guide_lead":"أعد مشروعك الأول ثم ضع الحدود التي تحافظ على صحته.","limits":"الحدود ووسائل الحماية","limits_text":"تحمي حدود المعدل الخدمة المشتركة وتجعل السعة سهلة الفهم.","api_title":"مرجع واجهة البرمجة","api_text":"يستخدم كل طلب JSON ونقطة نهاية ذات إصدار.","faq_title":"الأسئلة الشائعة","faq_text":"إجابات قصيرة عن الأسئلة التي تصل أولاً.","related":"أسئلة ذات صلة","related_text":"كيف أبدّل رمزًا؟ · أين أرى الاستخدام؟","read":"اقرأ الدليل"},
}


class DocsSite:
    name = "docs"
    title = "Northstar Docs"
    planted = [
        Planted("untranslated", "locale", "/guide", "Arabic renders one guide heading as its translation key."),
        Planted("low_contrast", "theme", "/", "Dark-only secondary help text uses #6b6b6b."),
        Planted("divergence", "viewport", "/faq", "Related questions disappear under 768px."),
    ]

    def handle(self, request: Request) -> Response:
        path = request.path.rstrip("/") or "/"
        if path not in {"/", "/guide", "/api", "/faq"}:
            return Response.not_found()
        return Response.html(self._page(_T[request.lang], request.lang, request.theme, path))

    def _page(self, t: dict[str, str], lang: str, theme: str, path: str) -> str:
        direction = "rtl" if lang == "ar" else "ltr"
        nav = "".join(f'<a href="{href}">{t[key]}</a>' for href, key in (("/", "home"), ("/guide", "guide"), ("/api", "api"), ("/faq", "faq")))
        pages = {"/": f'<p class="kicker">{t["eyebrow"]}</p><h1>{t["headline"]}</h1><p class="lead">{t["lead"]}</p><p class="help-text">{t["help"]}</p><a class="cta" href="/guide">{t["read"]} →</a>', "/guide": self._guide(t, lang), "/api": f'<p class="kicker">{t["eyebrow"]}</p><h1>{t["api_title"]}</h1><p class="lead">{t["api_text"]}</p><pre><code>GET /v1/projects</code></pre>', "/faq": self._faq(t)}
        return f'''<!doctype html><html lang="{lang}" dir="{direction}" data-theme="{theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{t["brand"]}</title><style>
*{{box-sizing:border-box}} :root{{--bg:#fbfaf6;--panel:#fff;--ink:#1f282a;--muted:#4c5a5b;--line:#d7ddda;--signal:#126b63;--help:#52605e}} [data-theme="dark"]{{--bg:#131b1d;--panel:#1c282a;--ink:#f1eee5;--muted:#c4ceca;--line:#3c4a4c;--signal:#8fd6c9;--help:#6b6b6b}} body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 Georgia,serif}} a{{color:inherit}} .wrap{{max-width:1050px;margin-inline:auto;padding-inline:28px}} header{{border-block-end:1px solid var(--line)}} .top{{min-height:72px;display:flex;align-items:center;justify-content:space-between;gap:28px}} .brand{{font:700 20px/1 Georgia,serif;text-decoration:none;letter-spacing:.03em}} nav{{display:flex;flex-wrap:wrap;gap:17px;font:700 13px/1 system-ui,sans-serif}} nav a{{text-decoration:none}} main{{max-width:760px;padding-block:68px 88px}} .kicker{{color:var(--signal);font:700 12px/1 system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase}} h1,h2{{line-height:1.12}} h1{{font-size:clamp(2.5rem,7vw,5.6rem);letter-spacing:-.035em;margin:13px 0 22px}} h2{{font-size:1.8rem;margin-block-start:48px}} .lead{{font-size:1.15rem;max-width:620px;color:var(--muted)}} .help-text{{margin-block:34px;color:var(--help);border-inline-start:3px solid var(--line);padding-inline-start:16px}} .cta{{display:inline-flex;margin-block-start:12px;background:var(--signal);color:#fff;padding:12px 17px;text-decoration:none;font:700 14px/1 system-ui,sans-serif}} [data-theme="dark"] .cta{{color:#07231f}} pre{{background:var(--panel);border:1px solid var(--line);padding:20px;overflow:auto}} .related-questions{{margin-block-start:44px;padding:22px;background:var(--panel);border:1px solid var(--line)}} @media (max-width:767px){{.related-questions{{display:none}} .wrap{{padding-inline:18px}} main{{padding-block:40px 58px}} .top{{align-items:flex-start;padding-block:18px}}}}
</style></head><body><header><div class="wrap top"><a class="brand" href="/">{t["brand"]}</a><nav aria-label="Primary">{nav}</nav></div></header><main class="wrap">{pages[path]}</main></body></html>'''

    def _guide(self, t: dict[str, str], lang: str) -> str:
        limits_heading = "guide.sections.limits.title" if lang == "ar" else t["limits"]
        return f'<p class="kicker">{t["guide"]}</p><h1>{t["guide_title"]}</h1><p class="lead">{t["guide_lead"]}</p><section><h2>{limits_heading}</h2><p>{t["limits_text"]}</p></section>'

    def _faq(self, t: dict[str, str]) -> str:
        return f'<p class="kicker">{t["faq"]}</p><h1>{t["faq_title"]}</h1><p class="lead">{t["faq_text"]}</p><section class="related-questions"><h2>{t["related"]}</h2><p>{t["related_text"]}</p></section>'
