/*
 * Parallax generated regression spec
 * Finding: render-baseline-7f4c5a1cb7cd5198-clipped
 * Axis: baseline
 * Evidence: owner-en-light-desktop=partial · member-en-light-desktop=partial · owner-en-dark-desktop=partial · owner-en-light-tablet=partial
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * Set PARALLAX_<ROLE>_STORAGE_STATE to the role state file before running this spec.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: process.env.PARALLAX_MEMBER_STORAGE_STATE,
});

test("Parallax: render-baseline-7f4c5a1cb7cd5198-clipped", async ({ page }) => {
  if (!process.env.PARALLAX_MEMBER_STORAGE_STATE) throw new Error("Parallax generated spec requires PARALLAX_MEMBER_STORAGE_STATE");
  const response = await page.goto("/about");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  expect(await page.locator("div.flex.items-center:nth-of-type(1) > div.flex.items-center:nth-of-type(2) > div.relative.hidden > button.group.flex > span.text-sm.font-medium").evaluate((element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight)).toBeTruthy();
});
