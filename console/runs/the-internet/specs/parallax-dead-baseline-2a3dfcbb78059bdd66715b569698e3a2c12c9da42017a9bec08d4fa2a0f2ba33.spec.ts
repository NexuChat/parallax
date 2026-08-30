/*
 * Parallax generated regression spec
 * Finding: dead-baseline-4934300727a6788f
 * Axis: baseline
 * Evidence: owner-en-light-desktop=blocked · owner-en-light-mobile=blocked · owner-en-light-tablet=blocked
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
});

test("Parallax: dead-baseline-4934300727a6788f", async ({ page }) => {
  const response = await page.goto("/basic_auth");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const reached = !isLoginPage && (response?.status() ?? 500) < 400;
  expect(reached).toBeTruthy();
});
