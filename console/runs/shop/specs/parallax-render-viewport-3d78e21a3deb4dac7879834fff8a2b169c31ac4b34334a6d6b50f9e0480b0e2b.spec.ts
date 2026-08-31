/*
 * Parallax generated regression spec
 * Finding: render-viewport-a10661cdf182b5a4-clipped
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

test("Parallax: render-viewport-a10661cdf182b5a4-clipped", async ({ page }) => {
  const response = await page.goto("/shop/product/organizer");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.locator("body > main.shell > section.product-layout:nth-of-type(1) > div:nth-of-type(2) > div.product-title-box.intentional-clip:nth-of-type(1)").evaluate((element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight)).toBeTruthy();
});
