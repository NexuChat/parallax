/*
 * Parallax generated regression spec
 * Finding: escalation-privilege-4674ffde453e7122
 * Axis: privilege
 * Evidence: owner-en-light-desktop=reached · anon-en-light-desktop=reached
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/anon.json",
});

test("Parallax: escalation-privilege-4674ffde453e7122", async ({ page }) => {
  const response = await page.goto("https://demo.mlki.app/workspace/audit");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const blocked = isLoginPage || response?.status() === 403 || false;
  expect(blocked).toBeTruthy();
});
