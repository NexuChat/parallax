/*
 * Parallax generated regression spec
 * Finding: render-viewport-7a4a1675f2fd8979
 * Axis: viewport
 * Evidence: owner-en-light-mobile=partial
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 360, height: 740 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: render-viewport-7a4a1675f2fd8979", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/admin/login?lang=en&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
});
