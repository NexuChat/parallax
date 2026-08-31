/*
 * Parallax generated regression spec
 * Finding: render-baseline-2cf4be103e26321f-clipped
 * Axis: baseline
 * Evidence: owner-en-light-desktop=partial · member-en-light-desktop=partial · anon-en-light-desktop=partial · owner-en-dark-desktop=partial · owner-en-light-mobile=partial · owner-en-light-tablet=partial
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
});

test("Parallax: render-baseline-2cf4be103e26321f-clipped", async ({ page }) => {
  const response = await page.goto("/auth?mode=register");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.locator("body > div > div.min-h-screen > div.min-h-screen.flex > div.fixed.inset-0:nth-of-type(1)").evaluate((element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight)).toBeTruthy();
});
