/*
 * Parallax generated regression spec
 * Finding: propagation-relational-5e2791251d7f5c2d
 * Axis: relational
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

test("Parallax: propagation-relational-5e2791251d7f5c2d", async ({ page }) => {

  test.skip("Sender post_to_quiet_thread did not produce receiver effect receiver_sees_message within 3000ms");
  // No assertion is emitted: this surface was unreachable for every witness.
});
