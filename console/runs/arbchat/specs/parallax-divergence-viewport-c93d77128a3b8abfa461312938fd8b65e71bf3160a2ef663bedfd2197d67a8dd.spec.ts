/*
 * Parallax generated regression spec
 * Finding: divergence-viewport-87e0e19271e196af
 * Axis: viewport
 * Evidence: owner-en-light-mobile=partial
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * Set PARALLAX_<ROLE>_STORAGE_STATE to the role state file before running this spec.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 360, height: 740 },
  locale: "en",
  colorScheme: "light",
  storageState: process.env.PARALLAX_OWNER_STORAGE_STATE,
});

test("Parallax: divergence-viewport-87e0e19271e196af", async ({ page }) => {
  if (!process.env.PARALLAX_OWNER_STORAGE_STATE) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
  const response = await page.goto("/faq");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const contentSignature = await page.evaluate(() => {
    const root = document.querySelector("main") ?? document.body;
    const text = (root.innerText || "").replace(/\s+/g, " ").trim();
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  });
  expect(contentSignature).toBe("e601820e");
});
