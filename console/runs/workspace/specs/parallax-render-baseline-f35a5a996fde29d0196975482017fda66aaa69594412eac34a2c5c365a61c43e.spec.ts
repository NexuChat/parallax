/*
 * Parallax generated regression spec
 * Finding: render-baseline-44d8e5e335763da4
 * Axis: baseline
 * Evidence: owner-en-light-desktop=partial · member-en-light-desktop=partial · owner-ar-light-desktop=partial · owner-en-dark-desktop=partial · owner-en-light-mobile=partial · owner-en-light-tablet=partial
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/member.json",
});

test("Parallax: render-baseline-44d8e5e335763da4", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/workspace/threads");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("button:nth-of-type(2)").boundingBox();
  expect(box).not.toBeNull();
  expect(await page.locator("button:nth-of-type(2)").evaluate((_, box) => box.x >= 0 && box.y >= 0 && box.x + box.width <= window.innerWidth && box.y + box.height <= window.innerHeight, box!)).toBeTruthy();
});
