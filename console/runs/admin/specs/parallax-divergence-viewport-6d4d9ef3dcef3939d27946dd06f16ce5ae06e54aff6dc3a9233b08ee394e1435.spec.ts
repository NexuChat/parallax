/*
 * Parallax generated regression spec
 * Finding: divergence-viewport-93a7bf9b6ff9f7d6
 * Axis: viewport
 * Evidence: owner-en-light-desktop=reached · owner-en-light-mobile=partial
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 360, height: 740 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: divergence-viewport-93a7bf9b6ff9f7d6", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/admin/users?lang=en&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const contentSignature = await page.evaluate(() => {
    const text = (document.body.innerText || "").replace(/\s+/g, " ").trim();
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  });
  expect(contentSignature).toBe("af118f02");
});
