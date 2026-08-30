/*
 * Parallax generated regression spec
 * Finding: inversion-privilege-207477bdfac60c0b
 * Axis: privilege
 * Evidence: owner-en-light-desktop=blocked · member-en-light-desktop=reached
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/owner.json",
});

test("Parallax: inversion-privilege-207477bdfac60c0b", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/admin/reports?lang=en&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const reached = !isLoginPage && (response?.status() ?? 500) < 400;
  expect(reached).toBeTruthy();
});
