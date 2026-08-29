import re

from demo.sites.base import Request
from demo.sites.shop import ShopSite


def body(path, **kwargs):
    response = ShopSite().handle(Request(path=path, **kwargs))
    assert response.status == 200
    return response.body.decode()


def test_shop_declares_exactly_the_four_intentional_defects():
    assert [(item.defect, item.axis, item.route) for item in ShopSite.planted] == [
        ("offscreen_control", "viewport", "/checkout"), ("horizontal_overflow", "viewport", "/cart"),
        ("small_tap_target", "viewport", "/cart"), ("clipped", "viewport", "/product/<id>"),
    ]


def test_shop_declares_no_login_accounts():
    assert ShopSite.accounts == []


def test_shop_checkout_intentionally_has_offscreen_place_order_at_360px():
    markup = body("/checkout")
    assert ".checkout-action-row" in markup and "width:720px" in markup and "flex-wrap:nowrap" in markup
    assert "Place order" in markup


def test_shop_cart_intentionally_has_horizontal_overflow_at_360px():
    assert ".cart-table" in body("/cart") and "min-width:720px" in body("/cart")


def test_shop_cart_intentionally_has_small_24px_quantity_tap_targets():
    markup = body("/cart")
    assert ".stepper button" in markup and "width:24px;height:24px" in markup


def test_shop_product_intentionally_clips_a_long_title():
    markup = body("/product/organizer")
    assert ".product-title-box" in markup and "height:2.35em;overflow:hidden" in markup
    assert "Modular walnut desk organizer" in markup


def test_shop_catalogue_is_responsive_and_does_not_leak_route_defects():
    markup = body("/")
    assert "@media (max-width:700px)" in markup
    assert all(token not in markup for token in ('class="cart-table"', 'class="checkout-action-row"', 'class="product-title-box"', 'class="stepper"'))


def test_shop_arabic_uses_rtl_and_unknown_paths_are_404():
    assert '<html lang="ar" dir="rtl"' in body("/", query={"lang": "ar"})
    assert ShopSite().handle(Request(path="/missing")).status == 404


def test_mounted_pages_keep_links_and_actions_within_shop():
    for path in ("/", "/cart"):
        markup = body(path, mount="/shop")
        assert all(url.startswith("/shop") for url in re.findall(r'(?:href|action)=["\']?([^"\' >]+)', markup))
