/*
 * Parallax generated regression spec
 * Finding: dead-baseline-cb4d02cf2083ed52
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

test("Parallax: dead-baseline-cb4d02cf2083ed52", async ({ page }) => {
  const response = await page.goto("/digest_auth");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const reached = !isLoginPage && (response?.status() ?? 500) < 400;
  expect(reached).toBeTruthy();
});
