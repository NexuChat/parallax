/*
 * Parallax generated cross-context geometry regression spec
 * Finding: render-locale-5e2791251d7f5c2d-rtl_not_mirrored
 * Axis: locale
 * Evidence: owner-en-light-desktop=reached · owner-ar-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 */
import { test, expect } from "@playwright/test";

test("Parallax: render-locale-5e2791251d7f5c2d-rtl_not_mirrored", async ({ browser }) => {
  const baseURL = test.info().project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("Parallax geometry specs require use.baseURL in playwright.config.ts");
  const baselineContext = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 900 },
    locale: "en",
    colorScheme: "light",
    storageState: (() => {
    const storageState = process.env.PARALLAX_OWNER_STORAGE_STATE;
    if (!storageState) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
    return storageState;
  })(),
  });
  const variantContext = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 900 },
    locale: "ar",
    colorScheme: "light",
    storageState: (() => {
    const storageState = process.env.PARALLAX_OWNER_STORAGE_STATE;
    if (!storageState) throw new Error("Parallax generated spec requires PARALLAX_OWNER_STORAGE_STATE");
    return storageState;
  })(),
  });
  try {
    const baselinePage = await baselineContext.newPage();
    const variantPage = await variantContext.newPage();
    await Promise.all([baselinePage.goto("/workspace/threads"), variantPage.goto("/workspace/threads")]);
    const [baselineBox, variantBox] = await Promise.all([
      baselinePage.locator("main.app-shell > section.thread-view > form.composer > div.composer-tools > span.composer-icon:nth-of-type(1)").boundingBox(),
      variantPage.locator("main.app-shell > section.thread-view > form.composer > div.composer-tools > span.composer-icon:nth-of-type(1)").boundingBox(),
    ]);
    expect(baselineBox).not.toBeNull();
    expect(variantBox).not.toBeNull();
  const variantViewportWidth = await variantPage.evaluate(() => window.innerWidth);
  const expectedVariantX = variantViewportWidth - baselineBox!.x - variantBox!.width;
  expect(Math.abs(variantBox!.x - expectedVariantX)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.y - baselineBox!.y)).toBeLessThanOrEqual(3);
  } finally {
    await Promise.all([baselineContext.close(), variantContext.close()]);
  }
});
