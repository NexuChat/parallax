/*
 * Parallax generated cross-context geometry regression spec
 * Finding: render-theme-ff441172c7f067c5-theme_layout_shift
 * Axis: theme
 * Evidence: owner-en-light-desktop=reached · owner-en-dark-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 */
import { test, expect } from "@playwright/test";

test("Parallax: render-theme-ff441172c7f067c5-theme_layout_shift", async ({ browser }) => {
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
    locale: "en",
    colorScheme: "dark",
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
      baselinePage.locator("html > body > header.site-header.threads-header").boundingBox(),
      variantPage.locator("html > body > header.site-header.threads-header").boundingBox(),
    ]);
    expect(baselineBox).not.toBeNull();
    expect(variantBox).not.toBeNull();
  expect(Math.abs(variantBox!.x - baselineBox!.x)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.y - baselineBox!.y)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.width - baselineBox!.width)).toBeLessThanOrEqual(3);
  expect(Math.abs(variantBox!.height - baselineBox!.height)).toBeLessThanOrEqual(3);
  } finally {
    await Promise.all([baselineContext.close(), variantContext.close()]);
  }
});
