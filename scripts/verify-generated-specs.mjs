#!/usr/bin/env node
/**
 * Execute every published generated Playwright spec and reject false-green
 * results caused by a missing role state, broken harness, or setup failure.
 */
import { spawnSync } from "node:child_process";
import { existsSync, lstatSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPOSITORY_ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));
const SPECS_ROOT = join(REPOSITORY_ROOT, "console", "runs");
const JSON_REPORTER = "--reporter=json";

function usage() {
  return `Usage: npm run verify:generated -- [options]

Runs every .spec.ts published under console/runs with Playwright's JSON reporter.
Intentional generated checks must all fail as assertions; storage, module, syntax,
browser, connection, skip, pass, or flaky outcomes fail this verification gate.

Options:
  --base-url URL       Target URL (or PARALLAX_BASE_URL)
  --owner-state PATH   Owner Playwright state (or PARALLAX_OWNER_STORAGE_STATE)
  --member-state PATH  Member Playwright state (or PARALLAX_MEMBER_STORAGE_STATE)
  --expected COUNT     Exact release-manifest spec count
  --runs a,b,c         Published runs to verify (default: the demo fleet)
  --report PATH        Write this gate's JSON result to PATH
  --help               Show this help
`;
}

function parseArguments(argv) {
  const options = { baseUrl: process.env.PARALLAX_BASE_URL, ownerState: process.env.PARALLAX_OWNER_STORAGE_STATE, memberState: process.env.PARALLAX_MEMBER_STORAGE_STATE, expected: undefined, report: undefined, runs: undefined };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help") return { help: true };
    const key = { "--base-url": "baseUrl", "--owner-state": "ownerState", "--member-state": "memberState", "--expected": "expected", "--report": "report", "--runs": "runs" }[arg];
    if (!key || index + 1 >= argv.length) throw new Error(`unknown or incomplete option: ${arg}`);
    options[key] = argv[index + 1];
    index += 1;
  }
  return options;
}

function generatedSpecs(directory) {
  const entries = readdirSync(directory, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return generatedSpecs(path);
    return entry.isFile() && entry.name.endsWith(".spec.ts") ? [path] : [];
  }).sort();
}

function regularState(path, role) {
  if (!path) return `${role} state missing (${role === "owner" ? "PARALLAX_OWNER_STORAGE_STATE" : "PARALLAX_MEMBER_STORAGE_STATE"})`;
  try {
    if (!lstatSync(path).isFile()) return `${role} state is not a regular file: ${path}`;
  } catch {
    return `${role} state does not exist: ${path}`;
  }
  return undefined;
}

function testsIn(suites) {
  return (suites ?? []).flatMap((suite) => [...(suite.specs ?? []).flatMap((spec) => spec.tests ?? []), ...testsIn(suite.suites)]);
}

function messageFor(test) {
  const result = test.results?.at(-1) ?? {};
  const error = result.error ?? test.error ?? {};
  return [error.message, error.stack, ...(result.errors ?? []).map((item) => item.message ?? item.stack ?? "")].filter(Boolean).join("\n");
}

function failureKind(message) {
  const lower = message.toLowerCase();
  if (/parallax_.*storage_state|storage state|enoent|eacces|cannot find module|module not found|syntaxerror|cannot use import|browser.*executable|econnrefused|net::err|config/.test(lower)) return "setup";
  if (/expect\(|assertionerror|tobe(?:truthy|falsy|visible|equal)|matcher error/.test(lower)) return "assertion";
  return "unclassified";
}

function resultSkeleton(expected) {
  return { expected, total: 0, failed: 0, passed: 0, skipped: 0, flaky: 0, assertion_failures: 0, setup_failures: [], unclassified_failures: [], global_errors: [], verdict: "FAIL" };
}

function summarize(report, expected) {
  const summary = resultSkeleton(expected);
  const tests = testsIn(report.suites);
  summary.total = tests.length;
  for (const test of tests) {
    const final = test.results?.at(-1) ?? {};
    const status = final.status ?? "unknown";
    if (status === "passed") summary.passed += 1;
    else if (status === "skipped") summary.skipped += 1;
    else if (status === "failed" || status === "timedOut" || status === "interrupted") {
      summary.failed += 1;
      const message = messageFor(test);
      const kind = failureKind(message);
      if (kind === "assertion") summary.assertion_failures += 1;
      else summary[`${kind}_failures`].push({ title: test.title, message: message.slice(0, 1200) });
    } else summary.unclassified_failures.push({ title: test.title, message: `unexpected final status: ${status}` });
    if ((test.results ?? []).some((item) => item.status === "failed") && status === "passed") summary.flaky += 1;
  }
  summary.global_errors = (report.errors ?? []).map((error) => (error.message ?? error.stack ?? String(error)).slice(0, 1200));
  const clean = summary.total === expected && summary.failed === expected && summary.passed === 0 && summary.skipped === 0 && summary.flaky === 0 && summary.assertion_failures === expected && summary.setup_failures.length === 0 && summary.unclassified_failures.length === 0 && summary.global_errors.length === 0;
  summary.verdict = clean ? "PASS" : "FAIL";
  return summary;
}

function output(summary, reportPath) {
  const serialized = `${JSON.stringify(summary, null, 2)}\n`;
  if (reportPath) writeFileSync(resolve(reportPath), serialized, "utf8");
  process.stdout.write(serialized);
}

function main() {
  let options;
  try {
    options = parseArguments(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error.message}\n${usage()}`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(usage());
    return 0;
  }
  // Only the runs named here. console/runs also holds sweeps of real sites —
  // arbchat.org, the-internet — whose specs address their own origin, and
  // running those against the demo fleet fails for a reason that has nothing to
  // do with whether spec generation works. `latest` is a copy of one demo run,
  // so including it would verify the same specs twice.
  const runs = (options.runs ?? "admin,arena,call,control,docs,shop,workspace")
    .split(",").map((name) => name.trim()).filter(Boolean);
  const specs = runs.flatMap((name) => {
    const directory = join(SPECS_ROOT, name);
    return existsSync(directory) ? generatedSpecs(directory) : [];
  }).sort();
  const expected = Number(options.expected);
  const summary = resultSkeleton(Number.isInteger(expected) && expected > 0 ? expected : 0);
  const stateErrors = [regularState(options.ownerState, "owner"), regularState(options.memberState, "member")].filter(Boolean);
  if (!options.baseUrl) stateErrors.push("base URL missing (PARALLAX_BASE_URL or --base-url)");
  if (!Number.isInteger(expected) || expected < 1) stateErrors.push("expected spec count missing or invalid (--expected COUNT)");
  else if (specs.length !== expected) stateErrors.push(`release manifest expects ${expected} specs, found ${specs.length}`);
  if (stateErrors.length) {
    summary.setup_failures = stateErrors.map((message) => ({ title: "environment", message }));
    output(summary, options.report);
    return 1;
  }
  const playwright = join(REPOSITORY_ROOT, "node_modules", "@playwright", "test", "cli.js");
  if (!existsSync(playwright)) {
    summary.setup_failures = [{ title: "harness", message: `Playwright harness missing: ${playwright}; run npm ci` }];
    output(summary, options.report);
    return 1;
  }
  // The spec paths are passed explicitly. Counting a scoped set and then letting
  // Playwright walk the whole testDir verified a different set than the one the
  // count was checked against — including sweeps of remote sites, whose specs
  // time out against the demo fleet and are reported as harness failures.
  const run = spawnSync(process.execPath, [playwright, "test", JSON_REPORTER, ...specs], {
    cwd: REPOSITORY_ROOT,
    encoding: "utf8",
    env: { ...process.env, PARALLAX_BASE_URL: options.baseUrl, PARALLAX_OWNER_STORAGE_STATE: resolve(options.ownerState), PARALLAX_MEMBER_STORAGE_STATE: resolve(options.memberState) },
  });
  if (run.error) {
    summary.setup_failures = [{ title: "harness", message: run.error.message }];
    output(summary, options.report);
    return 1;
  }
  let report;
  try {
    report = JSON.parse(run.stdout);
  } catch {
    summary.setup_failures = [{ title: "reporter", message: `Playwright JSON reporter did not produce valid JSON: ${(run.stderr || run.stdout).slice(0, 1200)}` }];
    output(summary, options.report);
    return 1;
  }
  const complete = summarize(report, expected);
  output(complete, options.report);
  return complete.verdict === "PASS" ? 0 : 1;
}

process.exitCode = main();
