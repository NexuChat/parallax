/*
 * Parallax generated regression spec
 * Finding: render-viewport-1c73ba87c9cc618e-horizontal_overflow
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

test("Parallax: render-viewport-1c73ba87c9cc618e-horizontal_overflow", async ({ page }) => {
  const response = await page.goto("/challenging_dom");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
