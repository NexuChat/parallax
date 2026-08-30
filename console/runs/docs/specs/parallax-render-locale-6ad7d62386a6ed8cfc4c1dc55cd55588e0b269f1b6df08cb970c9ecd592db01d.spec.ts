/*
 * Parallax generated regression spec
 * Finding: render-locale-899fcaa62a0a9a05-untranslated
 * Axis: locale
 * Evidence: owner-en-light-desktop=reached · owner-ar-light-desktop=partial · translation degraded: DefaultCredentialsError: Your default credentials were not found. To set up Application Default Credentials, see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.; deterministic raw-text fallback
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 * This run had no credentials for that role, so the spec opens the page anonymously.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "ar",
  colorScheme: "light",
});

test("Parallax: render-locale-899fcaa62a0a9a05-untranslated", async ({ page }) => {
  const response = await page.goto("/docs/guide");
  const isLoginPage = /\/(?:login|sign-in|auth)(?:[/?#]|$)/i.test(new URL(page.url()).pathname);
  const rawI18nKey = await page.locator("#limits").evaluate((element) => {
    const text = (element.textContent ?? "").trim();
    const rawKey = /(⟦[^⟧]+⟧)|(\{\{[^}]+\}\})|(^[a-z][a-z0-9]*(\.[a-z0-9_]+){2,}$)/i.test(text);
    const latin = text.match(/\b[A-Za-z]{3,}\b/g) ?? [];
    return rawKey || (document.documentElement.lang.toLowerCase().startsWith("ar") && latin.length >= 2 && !/[@/\\_]|\d{3,}/.test(text));
  });
  expect(rawI18nKey).toBeFalsy();
});
