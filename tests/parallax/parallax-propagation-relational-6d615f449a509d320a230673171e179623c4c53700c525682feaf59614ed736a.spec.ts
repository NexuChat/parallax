/*
 * Parallax generated relational regression spec
 * Finding: propagation-relational-59e0845cae72f335
 * Axis: relational
 * Evidence: owner-en-light-desktop=reached · member-en-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 */
import { test, expect } from "@playwright/test";

test("Parallax: propagation-relational-59e0845cae72f335", async ({ browser }) => {
  const baseURL = test.info().project.use.baseURL;
  if (typeof baseURL !== "string") throw new Error("Parallax relational specs require use.baseURL in playwright.config.ts");
  const senderContext = await browser.newContext({
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
  const receiverContext = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 900 },
    locale: "en",
    colorScheme: "light",
    storageState: (() => {
    const storageState = process.env.PARALLAX_MEMBER_STORAGE_STATE;
    if (!storageState) throw new Error("Parallax generated spec requires PARALLAX_MEMBER_STORAGE_STATE");
    return storageState;
  })(),
  });
  try {
    const senderPage = await senderContext.newPage();
    const receiverPage = await receiverContext.newPage();
    await Promise.all([senderPage.goto("/workspace/settings"), receiverPage.goto("/workspace/settings")]);
  await senderPage.locator("input[name=\"digest\"]").check();
  await senderPage.locator("form.settings-form").evaluate((form: HTMLFormElement) => form.requestSubmit());
  await expect.poll(async () => await receiverPage.locator("form.settings-form").isVisible().catch(() => false), { timeout: 5000 }).toBeTruthy();
  } finally {
    await Promise.all([senderContext.close(), receiverContext.close()]);
  }
});
