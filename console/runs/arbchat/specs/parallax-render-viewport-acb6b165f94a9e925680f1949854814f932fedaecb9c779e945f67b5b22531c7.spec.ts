/*
 * Parallax generated regression spec
 * Finding: render-viewport-8f7469b3d4e05316-small_tap_target
 * Axis: viewport
 * Evidence: owner-en-light-mobile=partial
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * Set PARALLAX_<ROLE>_STORAGE_STATE to the role state file before running this spec.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 360, height: 740 },
  locale: "en",
  colorScheme: "light",
  storageState: process.env.PARALLAX_OWNER_STORAGE_STATE,
});

test("Parallax: render-viewport-8f7469b3d4e05316-small_tap_target", async ({ page }) => {
  if (!process.env.PARALLAX_OWNER_STORAGE_STATE) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
  const response = await page.goto("/");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const box = await page.locator("div.max-w-[1240px].mx-auto:nth-of-type(2) > div.text-center.lg:text-start:nth-of-type(1) > div.mt-10.space-y-4:nth-of-type(4) > div.flex.justify-center:nth-of-type(2) > a.inline-flex.items-center").boundingBox();
  expect(box).not.toBeNull();
  expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44);
});
