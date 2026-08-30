/*
 * Parallax generated relational regression spec
 * Finding: revocation-relational-ff441172c7f067c5
 * Axis: relational
 * Evidence: owner-en-light-desktop=reached · member-en-light-desktop=reached
 * In playwright.config.ts: use: { baseURL: "https://your-app.example" }
 */
import { test, expect } from "@playwright/test";

test("Parallax: revocation-relational-ff441172c7f067c5", async ({ browser }) => {
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
    await Promise.all([senderPage.goto("/workspace/threads"), receiverPage.goto("/workspace/threads")]);
  expect(await receiverPage.evaluate(async (expectation) => {
      const response = await fetch(new URL(expectation.url, location.href));
      if (!response.ok) return false;
      const payload = await response.json();
      return Array.isArray(payload[expectation.items]) && payload[expectation.items]
        .some((item) => item && item[expectation.field] === expectation.equals);
    }, { url: "api/messages?since=0", items: "messages", field: "text", equals: "I can take the handoff copy before lunch." })).toBeTruthy();
  await senderPage.locator("form.revoke-form").evaluate((form: HTMLFormElement) => form.requestSubmit());
  const revocationCompletedAt = performance.now();
  await expect.poll(async () => await receiverPage.evaluate(async (expectation) => {
      const response = await fetch(new URL(expectation.url, location.href));
      if (!response.ok) return false;
      const payload = await response.json();
      return Array.isArray(payload[expectation.items]) && payload[expectation.items]
        .some((item) => item && item[expectation.field] === expectation.equals);
    }, { url: "api/messages?since=0", items: "messages", field: "text", equals: "I can take the handoff copy before lunch." }), { timeout: 15000 }).toBeFalsy();
  const revocationLagMs = performance.now() - revocationCompletedAt;
  expect(revocationLagMs).toBeLessThanOrEqual(100);
  } finally {
    await Promise.all([senderContext.close(), receiverContext.close()]);
  }
});
