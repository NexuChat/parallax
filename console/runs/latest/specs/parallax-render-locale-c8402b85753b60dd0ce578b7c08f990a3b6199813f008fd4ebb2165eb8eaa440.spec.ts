/*
 * Parallax generated regression spec
 * Finding: render-locale-22d481ed88f6d65e
 * Axis: locale
 * Evidence: owner-ar-light-desktop=partial
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "ar",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: render-locale-22d481ed88f6d65e", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/workspace/billing");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("body").boundingBox();
  expect(box).not.toBeNull();
  expect(await page.locator("body").evaluate((_, box) => box.x >= 0 && box.y >= 0 && box.x + box.width <= window.innerWidth && box.y + box.height <= window.innerHeight, box!)).toBeTruthy();
});
