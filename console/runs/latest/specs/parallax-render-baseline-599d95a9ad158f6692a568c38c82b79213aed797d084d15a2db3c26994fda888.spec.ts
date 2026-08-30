/*
 * Parallax generated regression spec
 * Finding: render-baseline-77a270a84508e993
 * Axis: baseline
 * Evidence: owner-en-light-desktop=blocked · member-en-light-desktop=blocked · owner-ar-light-desktop=blocked · owner-en-dark-desktop=blocked · owner-en-light-mobile=blocked · owner-en-light-tablet=blocked
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/member.json",
});

test("Parallax: render-baseline-77a270a84508e993", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/workspace/threads");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("button:nth-of-type(1)").boundingBox();
  expect(box).not.toBeNull();
  expect(await page.locator("button:nth-of-type(1)").evaluate((_, box) => box.x >= 0 && box.y >= 0 && box.x + box.width <= window.innerWidth && box.y + box.height <= window.innerHeight, box!)).toBeTruthy();
});
