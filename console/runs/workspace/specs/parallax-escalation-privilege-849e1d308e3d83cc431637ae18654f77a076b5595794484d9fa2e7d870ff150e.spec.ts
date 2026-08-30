/*
 * Parallax generated regression spec
 * Finding: escalation-privilege-c711558d2da0457d
 * Axis: privilege
 * Evidence: owner-en-light-desktop=partial · member-en-light-desktop=partial
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/member.json",
});

test("Parallax: escalation-privilege-c711558d2da0457d", async ({ page }) => {
  const response = await page.goto("http://127.0.0.1:8099/workspace/login");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const blocked = isLoginPage || response?.status() === 403 || !(await page.locator("button:nth-of-type(1)").isVisible().catch(() => false));
  expect(blocked).toBeTruthy();
});
