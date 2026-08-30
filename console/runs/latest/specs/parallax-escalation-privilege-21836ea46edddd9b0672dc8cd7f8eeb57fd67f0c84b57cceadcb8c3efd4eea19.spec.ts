/*
 * Parallax generated regression spec
 * Finding: escalation-privilege-6aaa19607c54a596
 * Axis: privilege
 * Evidence: owner-en-light-desktop=reached · anon-en-light-desktop=reached · anon-en-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
});

test("Parallax: escalation-privilege-6aaa19607c54a596", async ({ page }) => {
  const response = await page.goto("/workspace/audit");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const blocked = isLoginPage || response?.status() === 403 || false;
  expect(blocked).toBeTruthy();
});
