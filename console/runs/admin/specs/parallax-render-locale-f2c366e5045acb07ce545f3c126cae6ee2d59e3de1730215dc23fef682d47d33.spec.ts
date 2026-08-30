/*
 * Parallax generated regression spec
 * Finding: render-locale-41ce1d7da9e2a27f
 * Axis: locale
 * Evidence: owner-ar-light-desktop=reached
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "ar",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: render-locale-41ce1d7da9e2a27f", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/admin/logout?lang=en&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.locator("html").getAttribute("dir")).toBe("rtl");
  expect(await page.locator("body").evaluate((element) => getComputedStyle(element).direction)).toBe("rtl");
});
