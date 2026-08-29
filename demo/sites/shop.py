"""A small multilingual shop used as an intentional responsive-test target."""

from __future__ import annotations

from html import escape

from .base import Planted, Request, Response


_COPY = {
    "en": {
        "brand": "Folio Supply", "catalogue": "Catalogue", "cart": "Cart", "checkout": "Checkout",
        "eyebrow": "Objects for focused work", "headline": "Tools that leave room to think.",
        "intro": "A compact collection of useful, enduring desk companions.", "view": "View product",
        "add": "Add to cart", "back": "Back to catalogue", "your_cart": "Your cart",
        "item": "Item", "quantity": "Quantity", "price": "Price", "subtotal": "Subtotal",
        "continue": "Continue shopping", "order": "Order summary", "secure": "A considered checkout",
        "shipping": "Shipping", "total": "Total", "place": "Place order", "details": "Product details", "checkout_note": "Your details are kept only long enough to prepare this order.", "items": "2 items",
        "not_found": "Not found",
    },
    "ar": {
        "brand": "فوليو للوازم", "catalogue": "الكتالوج", "cart": "السلة", "checkout": "إتمام الشراء",
        "eyebrow": "أدوات للعمل المركز", "headline": "أدوات تترك مساحة للتفكير.",
        "intro": "مجموعة صغيرة من رفاق المكتب المفيدين والدائمين.", "view": "عرض المنتج",
        "add": "أضف إلى السلة", "back": "العودة إلى الكتالوج", "your_cart": "سلتك",
        "item": "المنتج", "quantity": "الكمية", "price": "السعر", "subtotal": "المجموع الفرعي",
        "continue": "متابعة التسوق", "order": "ملخص الطلب", "secure": "إتمام شراء مدروس",
        "shipping": "الشحن", "total": "الإجمالي", "place": "إرسال الطلب", "details": "تفاصيل المنتج", "checkout_note": "تُحفظ بياناتك فقط للمدة اللازمة لتجهيز هذا الطلب.", "items": "منتجان",
        "not_found": "غير موجود",
    },
}

_PRODUCTS = {
    "ledger": {"en": ("Ledger notebook", "A lay-flat notebook with a quiet dot grid.", "$18"), "ar": ("دفتر ليدجر", "دفتر يفتح بشكل مسطح مع شبكة نقاط هادئة.", "18 دولار")},
    "lamp": {"en": ("Beacon desk lamp", "Warm, directional light for the final hour.", "$64"), "ar": ("مصباح بيكون للمكتب", "ضوء دافئ وموجّه للساعة الأخيرة.", "64 دولار")},
    "organizer": {"en": ("Modular walnut desk organizer with letter tray and cable channel", "A long-lived place for the small things that otherwise wander.", "$82"), "ar": ("منظم مكتب معياري من الجوز مع صينية رسائل وقناة للكابلات", "مكان دائم للأشياء الصغيرة التي تتوه عادةً.", "82 دولار")},
}


class ShopSite:
    name = "shop"
    title = "Folio Supply"
    planted = [
        Planted("offscreen_control", "viewport", "/checkout", "The fixed 720px action row puts Place order beyond 360px."),
        Planted("horizontal_overflow", "viewport", "/cart", "The cart table has a fixed minimum width."),
        Planted("small_tap_target", "viewport", "/cart", "Quantity steppers are deliberately 24 by 24 pixels."),
        Planted("clipped", "viewport", "/product/<id>", "Long product names are clipped by a fixed-height title box."),
    ]

    def handle(self, request: Request) -> Response:
        lang, theme = request.lang, request.theme
        copy = _COPY[lang]
        path = request.path.rstrip("/") or "/"
        if path == "/":
            content = self._catalogue(copy, lang)
        elif path == "/cart":
            content = self._cart(copy, lang)
        elif path == "/checkout":
            content = self._checkout(copy)
        elif path.startswith("/product/") and path.removeprefix("/product/") in _PRODUCTS:
            content = self._product(copy, lang, path.removeprefix("/product/"))
        else:
            return Response.not_found()
        return Response.html(self._page(copy, lang, theme, content))

    def _page(self, copy: dict[str, str], lang: str, theme: str, content: str) -> str:
        direction = "rtl" if lang == "ar" else "ltr"
        nav = "".join(f'<a href="{href}">{copy[label]}</a>' for href, label in (("/", "catalogue"), ("/cart", "cart"), ("/checkout", "checkout")))
        return f'''<!doctype html><html lang="{lang}" dir="{direction}" data-theme="{theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{copy["brand"]}</title><style>
*{{box-sizing:border-box}} :root{{--paper:#f5f0e6;--ink:#172322;--muted:#59645f;--line:#cbd0c4;--accent:#b64c2d;--card:#fffdf8}} [data-theme="dark"]{{--paper:#16201f;--ink:#f4eddf;--muted:#b9c5bb;--line:#3f4d48;--accent:#f19b77;--card:#202c29}} body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 Georgia,serif}} a{{color:inherit}} .shell{{max-width:1120px;margin-inline:auto;padding-inline:24px}} header{{border-block-end:1px solid var(--line)}} .bar{{min-height:76px;display:flex;align-items:center;justify-content:space-between;gap:24px}} .brand{{font:700 22px/1 Georgia,serif;letter-spacing:.03em;text-decoration:none}} nav{{display:flex;flex-wrap:wrap;gap:18px;font:600 14px/1.2 system-ui,sans-serif}} nav a{{text-decoration:none}} main{{padding-block:56px 72px}} .eyebrow{{color:var(--accent);font:700 12px/1 system-ui,sans-serif;letter-spacing:.13em;text-transform:uppercase}} h1,h2{{line-height:1.08;margin:0}} h1{{font-size:clamp(2.4rem,7vw,5.3rem);max-width:760px;margin-block:14px}} h2{{font-size:clamp(1.65rem,4vw,2.6rem)}} .intro{{max-width:560px;color:var(--muted);font-size:1.08rem}} .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-block-start:44px}} .card,.summary{{border:1px solid var(--line);background:var(--card);padding:24px}} .swatch{{aspect-ratio:1.35;background:linear-gradient(135deg,#d9b88c,#7c4732);margin-block-end:20px}} .card:nth-child(2) .swatch{{background:linear-gradient(135deg,#dfd0a7,#956333)}} .card:nth-child(3) .swatch{{background:linear-gradient(135deg,#d8d0be,#704d3a)}} .card h2{{font-size:1.4rem}} .price{{font:700 1.1rem system-ui,sans-serif}} .button{{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding-inline:18px;background:var(--accent);color:#fffaf3;border:0;text-decoration:none;font:700 14px/1 system-ui,sans-serif}} .text-link{{color:var(--accent);font-weight:bold}} .product-layout,.checkout-layout{{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(260px,.75fr);gap:36px}} .product-art{{aspect-ratio:1.1;background:linear-gradient(135deg,#d7c4a5,#8a5c42)}} .product-title-box{{height:2.35em;overflow:hidden;margin-block:18px 10px}} .cart-table{{width:100%;min-width:720px;border-collapse:collapse}} th,td{{padding:16px;text-align:start;border-block-end:1px solid var(--line)}} th{{font:700 12px/1 system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase}} .stepper{{display:inline-flex;align-items:center;gap:8px}} .stepper button{{width:24px;height:24px;padding:0;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:16px}} .checkout-action-row{{display:flex;align-items:center;justify-content:space-between;gap:28px;width:720px;flex-wrap:nowrap;margin-block-start:28px}} .checkout-action-row .button{{flex:0 0 auto}} .summary p{{display:flex;justify-content:space-between;gap:20px}} .summary p:last-child{{border-block-start:1px solid var(--line);padding-block-start:14px;font-weight:bold}} @media (max-width:700px){{.shell{{padding-inline:18px}} main{{padding-block:36px 54px}} .grid,.product-layout,.checkout-layout{{grid-template-columns:1fr}} .bar{{align-items:flex-start;padding-block:18px}} .cart-table{{font-size:14px}}}}
</style></head><body><header><div class="shell bar"><a class="brand" href="/">{copy["brand"]}</a><nav aria-label="Primary">{nav}</nav></div></header><main class="shell">{content}</main></body></html>'''

    def _catalogue(self, copy: dict[str, str], lang: str) -> str:
        cards = "".join(f'<article class="card"><div class="swatch" aria-hidden="true"></div><h2>{escape(values[lang][0])}</h2><p>{escape(values[lang][1])}</p><p class="price">{values[lang][2]}</p><a class="text-link" href="/product/{key}">{copy["view"]} →</a></article>' for key, values in _PRODUCTS.items())
        return f'<p class="eyebrow">{copy["eyebrow"]}</p><h1>{copy["headline"]}</h1><p class="intro">{copy["intro"]}</p><section class="grid">{cards}</section>'

    def _product(self, copy: dict[str, str], lang: str, product_id: str) -> str:
        title, description, price = _PRODUCTS[product_id][lang]
        return f'<a class="text-link" href="/">← {copy["back"]}</a><section class="product-layout" style="margin-block-start:26px"><div class="product-art" aria-hidden="true"></div><div><p class="eyebrow">{copy["details"]}</p><div class="product-title-box"><h1>{escape(title)}</h1></div><p class="intro">{escape(description)}</p><p class="price">{price}</p><a class="button" href="/cart">{copy["add"]}</a></div></section>'

    def _cart(self, copy: dict[str, str], lang: str) -> str:
        ledger, lamp = _PRODUCTS["ledger"][lang][0], _PRODUCTS["lamp"][lang][0]
        return f'''<h1>{copy["your_cart"]}</h1><table class="cart-table"><thead><tr><th>{copy["item"]}</th><th>{copy["quantity"]}</th><th>{copy["price"]}</th><th>{copy["subtotal"]}</th></tr></thead><tbody><tr><td>{ledger}</td><td><span class="stepper"><button aria-label="Decrease quantity">−</button><span>1</span><button aria-label="Increase quantity">+</button></span></td><td>$18</td><td>$18</td></tr><tr><td>{lamp}</td><td><span class="stepper"><button aria-label="Decrease quantity">−</button><span>1</span><button aria-label="Increase quantity">+</button></span></td><td>$64</td><td>$64</td></tr></tbody></table><p><a class="text-link" href="/">← {copy["continue"]}</a></p><a class="button" href="/checkout">{copy["checkout"]}</a>'''

    def _checkout(self, copy: dict[str, str]) -> str:
        return f'<section class="checkout-layout"><div><p class="eyebrow">{copy["secure"]}</p><h1>{copy["checkout"]}</h1><p class="intro">{copy["checkout_note"]}</p><div class="checkout-action-row"><a class="text-link" href="/cart">← {copy["cart"]}</a><button class="button">{copy["place"]}</button></div></div><aside class="summary"><h2>{copy["order"]}</h2><p><span>{copy["items"]}</span><span>$82</span></p><p><span>{copy["shipping"]}</span><span>$8</span></p><p><span>{copy["total"]}</span><span>$90</span></p></aside></section>'
