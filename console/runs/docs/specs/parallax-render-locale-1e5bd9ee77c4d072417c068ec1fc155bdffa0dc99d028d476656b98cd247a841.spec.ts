/*
 * Parallax generated regression spec
 * Finding: render-locale-2440b579ef376920
 * Axis: locale
 * Evidence: owner-ar-light-desktop=blocked
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "ar",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: render-locale-2440b579ef376920", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/docs/guide");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const rawI18nKey = await page.locator("body").evaluate((element) => /\b[a-z][\w-]*(?:\.[a-z][\w-]*)+\b/i.test(element.textContent ?? ""));
  expect(rawI18nKey).toBeFalsy();
});
