/*
 * Parallax generated regression spec
 * Finding: render-viewport-32e69bb3cd2df3b1-offscreen_control
 * Axis: viewport
 * Evidence: owner-en-light-mobile=partial
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 360, height: 740 },
  locale: "en",
  colorScheme: "light",
});

test("Parallax: render-viewport-32e69bb3cd2df3b1-offscreen_control", async ({ page }) => {
  const response = await page.goto("/shop/checkout");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const withinViewport = await page.locator("section.checkout-layout > form.checkout-form > div.checkout-action-clip:nth-of-type(2) > div.checkout-action-row > button.button").evaluate((element) => {
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.right <= window.innerWidth;
  });
  expect(withinViewport).toBeTruthy();
});
