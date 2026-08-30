/*
 * Parallax generated regression spec
 * Finding: divergence-viewport-5e5efcd1db114c97
 * Axis: viewport
 * Evidence: owner-en-light-desktop=partial · owner-en-light-tablet=partial · semantic comparison degraded: changed visible region was not captured; falling back to hash mismatch
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 768, height: 1024 },
  locale: "en",
  colorScheme: "light",
});

test("Parallax: divergence-viewport-5e5efcd1db114c97", async ({ page }) => {
  const response = await page.goto("/disappearing_elements");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const contentSignature = await page.evaluate(() => {
    const root = document.querySelector("main") ?? document.body;
    const text = (root.innerText || "").replace(/\s+/g, " ").trim();
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  });
  expect(contentSignature).toBe("ed388180");
});
