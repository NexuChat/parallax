/*
 * Parallax generated regression spec
 * Finding: render-viewport-1c73ba87c9cc618e-offscreen_control
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

test("Parallax: render-viewport-1c73ba87c9cc618e-offscreen_control", async ({ page }) => {
  const response = await page.goto("/challenging_dom");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const withinViewport = await page.locator("table > tbody > tr:nth-of-type(1) > td:nth-of-type(7) > a:nth-of-type(1)").evaluate((element) => {
    const box = element.getBoundingClientRect();
    return box.left >= 0 && box.right <= window.innerWidth;
  });
  expect(withinViewport).toBeTruthy();
});
