/*
 * Parallax generated regression spec
 * Finding: inversion-privilege-71ba741747ef492a
 * Axis: privilege
 * Evidence: owner-en-light-desktop=blocked · member-en-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * Set PARALLAX_<ROLE>_STORAGE_STATE to the role state file before running this spec.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: process.env.PARALLAX_OWNER_STORAGE_STATE,
});

test("Parallax: inversion-privilege-71ba741747ef492a", async ({ page }) => {
  if (!process.env.PARALLAX_OWNER_STORAGE_STATE) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
  const response = await page.goto("/admin/reports?lang=en&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const reached = !isLoginPage && (response?.status() ?? 500) < 400;
  expect(reached).toBeTruthy();
});
