/*
 * Parallax generated regression spec
 * Finding: render-locale-c711558d2da0457d
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

test("Parallax: render-locale-c711558d2da0457d", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/workspace/login");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const contrastRatio = await page.locator("button:nth-of-type(1)").evaluate((element) => {
    const rgb = (value: string) => value.match(/\d+(?:\.\d+)?/g)?.slice(0, 3).map(Number) ?? [0, 0, 0];
    const luminance = (color: number[]) => color.map(channel => { const s = channel / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }).reduce((total, channel, index) => total + channel * [0.2126, 0.7152, 0.0722][index], 0);
    const style = getComputedStyle(element); const a = luminance(rgb(style.color)); const b = luminance(rgb(style.backgroundColor));
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  });
  expect(contrastRatio).toBeGreaterThanOrEqual(4.5);
});
