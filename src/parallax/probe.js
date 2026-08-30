/**
 * The deterministic probe.
 *
 * Everything measurable is measured here, in the page, for free — no screenshot,
 * no model call, no judgement. Vision is expensive and non-repeatable; geometry
 * is neither. Whatever this file can decide, the model never needs to see.
 *
 * Returns a snapshot the differ and the specialists consume: defects that stand
 * on their own, plus the element geometry the mirror test compares across
 * locales and the layout signature that must not move when only the theme does.
 */
(() => {
  const MIN_TAP_TARGET = 44;        // WCAG 2.2 target size (minimum)
  const AA_NORMAL = 4.5;            // WCAG AA contrast for normal text
  const AA_LARGE = 3.0;             // ...and for large text
  const LARGE_PX = 24;

  const view = {
    width: window.innerWidth,
    height: window.innerHeight,
    dir: document.documentElement.getAttribute('dir')
      || getComputedStyle(document.documentElement).direction,
    lang: document.documentElement.lang || null,
  };

  const defects = [];
  const add = (type, detail, selector) => defects.push({ type, detail, selector });

  const hasMediaQuery = (needle) => {
    const hasRule = (rules) => [...rules].some((rule) => {
      const condition = `${rule.conditionText || ''} ${rule.media ? rule.media.mediaText : ''}`.toLowerCase();
      if (condition.includes(needle)) return true;
      try { return rule.cssRules && hasRule(rule.cssRules); } catch (_) { return false; }
    });
    return [...document.styleSheets].some((sheet) => {
      try { return hasRule(sheet.cssRules); } catch (_) { return false; }
    });
  };
  const controlMentions = (pattern) => [...document.querySelectorAll(
    'button, input, select, [role="button"], [aria-pressed]'
  )].some((element) => pattern.test([
    element.id, element.className, element.getAttribute('name'), element.getAttribute('aria-label'),
    element.getAttribute('title'), element.textContent,
  ].filter(Boolean).join(' ')));
  const visibleText = document.body ? document.body.innerText : '';
  const nonLatinText = [...visibleText].some((character) =>
    /\p{Letter}/u.test(character) && !/\p{Script=Latin}/u.test(character)
  );
  const support = {
    localeAlternate: Boolean(document.querySelector('link[rel~="alternate"][hreflang], a[rel~="alternate"][hreflang]')),
    languageSwitcher: Boolean(document.querySelector('a[hreflang]')) || controlMentions(/\b(language|locale|lang)\b/i),
    nonLatinText,
    themeMedia: hasMediaQuery('prefers-color-scheme'),
    themeToggle: controlMentions(/\b(theme|dark mode|light mode|color scheme)\b/i),
    viewportMeta: Boolean(document.querySelector('meta[name="viewport"]')),
    viewportMedia: hasMediaQuery('width'),
  };

  // ---------------------------------------------------------------- selectors
  const pathTo = (el) => {
    if (!el || el.nodeType !== 1) return null;
    if (el.id) return `#${el.id}`;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 5) {
      let part = node.tagName.toLowerCase();
      if (node.classList.length) part += `.${[...node.classList].slice(0, 2).join('.')}`;
      const siblings = node.parentElement
        ? [...node.parentElement.children].filter((c) => c.tagName === node.tagName)
        : [];
      if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };

  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  // ------------------------------------------------------------- 1. overflow
  // A page wider than its own viewport means a horizontal scrollbar the design
  // did not ask for. Measured, not guessed.
  const docWidth = document.documentElement.scrollWidth;
  if (docWidth > view.width + 1) {
    // Name the widest offender rather than just reporting "something overflows".
    let worst = null;
    let worstRight = view.width;
    for (const el of document.body.querySelectorAll('*')) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      const right = view.dir === 'rtl' ? -r.left : r.right;
      if (right > worstRight + 1) { worstRight = right; worst = el; }
    }
    add('horizontal_overflow',
        { pageWidth: docWidth, viewport: view.width, overflowBy: docWidth - view.width },
        pathTo(worst));
  }

  // --------------------------------------------------- 2. offscreen controls
  // An actionable element outside the viewport is not "hard to reach"; it is
  // unusable. This is the defect that most often only appears at 360px.
  const actionable = [...document.querySelectorAll(
    'button, a[href], input, select, textarea, [role="button"], [onclick]'
  )].filter(visible);

  for (const el of actionable) {
    const r = el.getBoundingClientRect();
    const absLeft = r.left + window.scrollX;
    if (absLeft + r.width < 0 || absLeft > document.documentElement.scrollWidth + 1) {
      add('offscreen_control', { left: Math.round(absLeft), width: Math.round(r.width) }, pathTo(el));
    }
    // Tap targets only matter where fingers are used.
    if (view.width <= 480 && (r.width < MIN_TAP_TARGET || r.height < MIN_TAP_TARGET)) {
      add('small_tap_target',
          { width: Math.round(r.width), height: Math.round(r.height), min: MIN_TAP_TARGET },
          pathTo(el));
    }
  }

  // ------------------------------------------------------------- 3. clipping
  for (const el of document.body.querySelectorAll('*')) {
    if (!visible(el)) continue;
    const s = getComputedStyle(el);
    if (s.overflow === 'visible') continue;
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 && el.children.length === 0) {
      add('clipped', { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }, pathTo(el));
    }
  }

  // ------------------------------------------------------------- 4. contrast
  const luminance = (rgb) => {
    const c = rgb.map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const parseColor = (value) => {
    const m = value.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((n) => parseFloat(n));
    if (parts.length === 4 && parts[3] === 0) return null;  // fully transparent
    return parts.slice(0, 3);
  };
  const backdrop = (el) => {
    // Walk up until an element actually paints a background.
    let node = el;
    while (node && node !== document.documentElement) {
      const bg = parseColor(getComputedStyle(node).backgroundColor);
      if (bg) return bg;
      node = node.parentElement;
    }
    return [255, 255, 255];
  };

  const textNodes = [...document.body.querySelectorAll('p, span, a, li, h1, h2, h3, h4, label, button, td')]
    .filter((el) => visible(el) && el.textContent.trim().length > 1)
    .slice(0, 400);   // bounded: this runs on every witness, every moment

  for (const el of textNodes) {
    const s = getComputedStyle(el);
    const fg = parseColor(s.color);
    if (!fg) continue;
    const ratio = (() => {
      const a = luminance(fg);
      const b = luminance(backdrop(el));
      const [hi, lo] = a > b ? [a, b] : [b, a];
      return (hi + 0.05) / (lo + 0.05);
    })();
    const size = parseFloat(s.fontSize);
    const bold = parseInt(s.fontWeight, 10) >= 700;
    const threshold = size >= LARGE_PX || (size >= 18.66 && bold) ? AA_LARGE : AA_NORMAL;
    if (ratio < threshold) {
      add('low_contrast',
          { ratio: Math.round(ratio * 100) / 100, required: threshold, fontSize: size },
          pathTo(el));
    }
  }

  // ------------------------------------------------- 5. untranslated strings
  // Two separate failures: a key that never resolved, and Latin prose sitting
  // in an Arabic UI. The second needs care — brand names and code are fine.
  const RAW_KEY = /(⟦[^⟧]+⟧)|(\{\{[^}]+\}\})|(^[a-z][a-z0-9]*(\.[a-z0-9_]+){2,}$)/i;
  const ARABIC = /[؀-ۿ]/;
  const LATIN_WORDS = /\b[A-Za-z]{3,}\b/g;

  for (const el of textNodes) {
    const text = el.textContent.trim();
    if (text.length > 120) continue;
    if (RAW_KEY.test(text)) {
      add('untranslated', { text: text.slice(0, 60), reason: 'raw_key' }, pathTo(el));
      continue;
    }
    if (view.lang && view.lang.startsWith('ar') && !ARABIC.test(text)) {
      const latin = text.match(LATIN_WORDS) || [];
      // Ignore short labels and anything that looks like an identifier or URL.
      if (latin.length >= 2 && !/[@/\\_]|\d{3,}/.test(text)) {
        add('untranslated', { text: text.slice(0, 60), reason: 'latin_in_arabic' }, pathTo(el));
      }
    }
  }

  // ------------------------------------------- 6. geometry for cross-context
  // Not defects — raw material. The mirror test flips these across locales; the
  // theme check requires them to be identical. Only stable, meaningful boxes.
  const geometry = [];
  const landmarks = [...document.querySelectorAll(
    'header, nav, main, footer, aside, section, button, a[href], h1, h2, [role]'
  )].filter(visible).slice(0, 120);

  for (const el of landmarks) {
    const r = el.getBoundingClientRect();
    geometry.push({
      selector: pathTo(el),
      tag: el.tagName.toLowerCase(),
      x: Math.round(r.left + window.scrollX),
      y: Math.round(r.top + window.scrollY),
      w: Math.round(r.width),
      h: Math.round(r.height),
      text: (el.textContent || '').trim().slice(0, 40),
    });
  }

  // A hash of what the page *says* and how it is *shaped*, kept separate so the
  // differ can ask "did the words change?" apart from "did the layout move?".
  const hash = (s) => {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  };

  return {
    view,
    url: location.pathname + location.search,
    title: document.title,
    defects,
    geometry,
    support,
    contentSignature: hash(document.body.innerText.replace(/\s+/g, ' ').trim()),
    layoutSignature: hash(geometry.map((g) => `${g.tag}:${g.x},${g.y},${g.w},${g.h}`).join('|')),
    consoleErrorCount: window.__parallaxConsoleErrors || 0,
  };
})();
