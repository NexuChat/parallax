/*
 * Parallax generated regression spec
 * Finding: escalation-privilege-4674ffde453e7122
 * Axis: privilege
 * Evidence: owner-en-light-desktop=reached · anon-en-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * storage-state convention: scripts/run_demo_suite.py writes runs/<site>/storage-<role>.json after login for member and owner; anonymous runs use no stored state.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
});

test("Parallax: escalation-privilege-4674ffde453e7122", async ({ page }) => {
  const response = await page.goto("/workspace/audit");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const blocked = isLoginPage || response?.status() === 403 || false;
  expect(blocked).toBeTruthy();
});
