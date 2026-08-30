/*
 * Parallax generated regression spec
 * Finding: render-viewport-5e5efcd1db114c97-small_tap_target
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

test("Parallax: render-viewport-5e5efcd1db114c97-small_tap_target", async ({ page }) => {
  const response = await page.goto("/disappearing_elements");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("body > div.row:nth-of-type(3) > div.large-4.large-centered > div > a").boundingBox();
  expect(box).not.toBeNull();
  expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44);
});
