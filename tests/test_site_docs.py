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


def test_docs_guide_intentionally_exposes_raw_translation_key_in_arabic():
    markup = body("/guide", query={"lang": "ar"})
    assert "guide.sections.limits.title" in markup
    assert "دليل عملي" in markup


def test_docs_home_intentionally_uses_low_contrast_help_text_only_in_dark_theme():
    dark = body("/", query={"theme": "dark"})
    light = body("/", query={"theme": "light"})
    assert "[data-theme=\"dark\"]" in dark and "--help:#6b6b6b" in dark
    assert ":root{--bg:#fbfaf6" in light and "--help:#52605e" in light


def test_docs_faq_intentionally_drops_related_questions_below_768px():
    markup = body("/faq")
    assert ".related-questions{display:none}" in markup
    assert "Related questions" in markup


def test_docs_arabic_is_rtl_and_unknown_paths_are_404():
    assert '<html lang="ar" dir="rtl"' in body("/api", query={"lang": "ar"})
    assert DocsSite().handle(Request(path="/nope")).status == 404
