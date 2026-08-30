/*
 * Parallax generated regression spec
 * Finding: drift-locale-a3005216b53e954d
 * Axis: locale
 * Evidence: owner-en-light-desktop=reached · owner-ar-light-desktop=blocked
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

test("Parallax: drift-locale-a3005216b53e954d", async ({ page }) => {
  if (!process.env.PARALLAX_OWNER_STORAGE_STATE) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
  const response = await page.goto("/admin/exports?lang=ar&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const reached = !isLoginPage && await page.locator("button:nth-of-type(1)").isVisible();
  expect(reached).toBeTruthy();
});
