/*
 * Parallax generated regression spec
 * Finding: render-viewport-2f6b52b20f4f1460
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

test("Parallax: render-viewport-2f6b52b20f4f1460", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/docs");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("button:nth-of-type(1)").boundingBox();
  expect(box).not.toBeNull();
  expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44);
});
