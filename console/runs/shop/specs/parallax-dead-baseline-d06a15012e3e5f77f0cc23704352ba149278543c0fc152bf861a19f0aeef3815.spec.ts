/*
 * Parallax generated regression spec
 * Finding: dead-baseline-266ea592eaa6b0e2
 * Axis: baseline
 * Evidence: owner-en-light-desktop=blocked · member-en-light-desktop=blocked · anon-en-light-desktop=blocked · owner-ar-light-desktop=blocked · owner-en-dark-desktop=blocked · owner-en-light-mobile=blocked · owner-en-light-tablet=blocked
 * storage-state convention: .auth/<role>.json supplies the browser state for anon, member, and owner.
 */
import { test, expect } from "@playwright/test";

test.use({
  viewport: { width: 1440, height: 900 },
  locale: "en",
  colorScheme: "light",
  storageState: ".auth/anon.json",
});

test("Parallax: dead-baseline-266ea592eaa6b0e2", async ({ page }) => {

  test.skip("no witness could reach \u2212 on http://127.0.0.1:8099/shop/cart");
  // No assertion is emitted: this surface was unreachable for every witness.
});
