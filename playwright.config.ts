import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./console/runs",
  testMatch: "**/*.spec.ts",
  use: {
    baseURL: process.env.PARALLAX_BASE_URL ?? "http://127.0.0.1:8080",
  },
});
