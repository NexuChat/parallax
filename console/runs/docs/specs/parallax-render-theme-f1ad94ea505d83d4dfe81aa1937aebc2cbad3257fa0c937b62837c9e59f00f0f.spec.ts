/*
 * Parallax generated regression spec
 * Finding: render-theme-7960fd401b12503d-low_contrast
 * Axis: theme
 * Evidence: owner-en-dark-desktop=partial
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "dark",
});

test("Parallax: render-theme-7960fd401b12503d-low_contrast", async ({ page }) => {
  const response = await page.goto("/docs");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const contrastRatio = await page.locator("html > body > main.shell > p.help-text:nth-of-type(3)").evaluate((element) => {
    const parseColor = (value: string) => {
      const match = value.match(/rgba?\(([^)]+)\)/);
      if (!match) return null;
      const channels = match[1].split(",").map(Number);
      if (channels.length === 4 && channels[3] === 0) return null;
      return channels.slice(0, 3);
    };
    const luminance = (color: number[]) => color.map(channel => { const s = channel / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }).reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0);
    const backdrop = () => {
      let background: Element | null = element;
      while (background && background !== document.documentElement) {
        const color = parseColor(getComputedStyle(background).backgroundColor);
        if (color) return color;
        background = background.parentElement;
      }
      return [255, 255, 255];
    };
    const foreground = parseColor(getComputedStyle(element).color);
    if (!foreground) throw new Error("Parallax could not parse the recorded element color");
    const a = luminance(foreground); const b = luminance(backdrop());
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  });
  expect(contrastRatio).toBeGreaterThanOrEqual(4.5);
});
