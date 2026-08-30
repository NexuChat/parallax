/*
 * Parallax generated regression spec
 * Finding: escalation-privilege-daf6769ed0636b9f
 * Axis: privilege
 * Evidence: owner-en-light-desktop=reached · member-en-light-desktop=reached
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/member.json",
});

test("Parallax: escalation-privilege-daf6769ed0636b9f", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/docs/faq");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const blocked = isLoginPage || response?.status() === 403 || false;
  expect(blocked).toBeTruthy();
});
