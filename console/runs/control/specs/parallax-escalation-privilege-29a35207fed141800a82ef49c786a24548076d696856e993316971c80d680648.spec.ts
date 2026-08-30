/*
 * Parallax generated regression spec
 * Finding: escalation-privilege-8f301d2ac72bb16e
 * Axis: privilege
 * Evidence: anon-en-light-desktop=blocked · member-en-light-desktop=reached
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/anon.json",
});

test("Parallax: escalation-privilege-8f301d2ac72bb16e", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/control/team?lang=en&theme=light");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const blocked = isLoginPage || response?.status() === 403 || false;
  expect(blocked).toBeTruthy();
});
