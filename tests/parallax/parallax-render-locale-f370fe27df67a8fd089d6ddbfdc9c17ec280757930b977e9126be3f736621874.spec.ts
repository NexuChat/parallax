/*
 * Parallax generated regression spec
 * Finding: render-locale-5e2791251d7f5c2d
 * Axis: locale
 * Evidence: owner-ar-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * Set PARALLAX_<ROLE>_STORAGE_STATE to the role state file before running this spec.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "ar",
  colorScheme: "light",
  storageState: process.env.PARALLAX_OWNER_STORAGE_STATE,
});

test("Parallax: render-locale-5e2791251d7f5c2d", async ({ page }) => {
  if (!process.env.PARALLAX_OWNER_STORAGE_STATE) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
  const response = await page.goto("/workspace/threads");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  throw new Error("Parallax render finding did not include a known defect");
});
