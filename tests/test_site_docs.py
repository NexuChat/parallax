import re

from demo.sites.base import Request
from demo.sites.docs import DocsSite


def body(path, **kwargs):
    response = DocsSite().handle(Request(path=path, **kwargs))
    assert response.status == 200
    return response.body.decode()


def test_docs_declares_exactly_the_three_intentional_defects():
    assert [(item.defect, item.axis, item.route) for item in DocsSite.planted] == [
        ("untranslated", "locale", "/guide"), ("low_contrast", "theme", "/"), ("divergence", "viewport", "/faq"),
    ]


def test_docs_declares_no_login_accounts():
    assert DocsSite.accounts == []


def test_docs_guide_intentionally_exposes_one_raw_translation_key_in_arabic():
    markup = body("/guide", query={"lang": "ar"})
    assert markup.count("guide.sections.limits.title") == 1
    assert "أطلق أول عملية نشر متتبعة" in markup


def test_docs_home_intentionally_uses_low_contrast_help_text_only_in_dark_theme():
    dark = body("/", query={"theme": "dark"})
    light = body("/", query={"theme": "light"})
    assert '[data-theme="dark"]' in dark and "--help:#6b6b6b" in dark
    assert ":root{--bg:#f5f7f5" in light and "--help:#52605e" in light


def test_docs_faq_intentionally_drops_related_questions_below_768px():
    markup = body("/faq")
    assert ".related-questions{display:none}" in markup
    assert "Related questions" in markup


def test_docs_routes_have_the_requested_product_reference_furniture():
    home = body("/")
    guide = body("/guide")
    api = body("/api")
    faq = body("/faq")
    assert '<form class="search-form"' in home and "Popular pages" in home and 'class="card-grid"' in home
    assert 'class="toc"' in guide and 'class="callout"' in guide and 'class="code-head"' in guide
    assert 'class="endpoint-row"' in api and 'class="param-table"' in api and "201 Created" in api
    assert faq.count("<details>") == 4 and 'class="related-questions"' in faq


def test_docs_arabic_is_rtl_and_unknown_paths_are_404():
    assert '<html lang="ar" dir="rtl"' in body("/api", query={"lang": "ar"})
    assert DocsSite().handle(Request(path="/nope")).status == 404


def test_mounted_pages_keep_links_and_actions_within_docs():
    for path in ("/", "/guide", "/faq"):
        markup = body(path, mount="/docs")
        assert all(url.startswith("/docs") for url in re.findall(r'(?:href|action)=["\']?([^"\' >]+)', markup))
