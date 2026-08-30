/*
 * Parallax generated regression spec
 * Finding: render-viewport-77a270a84508e993
 * Axis: viewport
 * Evidence: owner-en-light-mobile=blocked
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 360, height: 740 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: render-viewport-77a270a84508e993", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/workspace/threads");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("button:nth-of-type(1)").boundingBox();
  expect(box).not.toBeNull();
  expect(await page.locator("button:nth-of-type(1)").evaluate((_, box) => box.x >= 0 && box.y >= 0 && box.x + box.width <= window.innerWidth && box.y + box.height <= window.innerHeight, box!)).toBeTruthy();
});
