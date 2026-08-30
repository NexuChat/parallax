/*
 * Parallax generated regression spec
 * Finding: render-locale-daf6769ed0636b9f
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

test("Parallax: render-locale-daf6769ed0636b9f", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/docs/faq");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.locator("html").getAttribute("dir")).toBe("rtl");
  expect(await page.locator("body").evaluate((element) => getComputedStyle(element).direction)).toBe("rtl");
});
