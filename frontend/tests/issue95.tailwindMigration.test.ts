import { execSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const FRONTEND_SRC = path.join(FRONTEND_ROOT, "src");
const THIS_FILE = fileURLToPath(import.meta.url);
const LEGACY_APP_STYLESHEET = `App${".css"}`;

const SOURCE_EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".css",
  ".html",
  ".json",
  ".md",
]);

function collectAppCssReferences(dir: string): string[] {
  const matches: string[] = [];

  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "dist") continue;
      matches.push(...collectAppCssReferences(fullPath));
      continue;
    }

    const extension = path.extname(entry.name);
    if (!SOURCE_EXTENSIONS.has(extension)) continue;

    const contents = readFileSync(fullPath, "utf-8");
    if (contents.includes(LEGACY_APP_STYLESHEET)) {
      matches.push(path.relative(FRONTEND_SRC, fullPath));
    }
  }

  return matches.sort();
}

function runNpmScript(script: string, extraArgs = ""): number {
  try {
    execSync(`npm run ${script}${extraArgs}`, {
      cwd: FRONTEND_ROOT,
      stdio: "pipe",
      encoding: "utf-8",
    });
    return 0;
  } catch (error) {
    const execError = error as { status?: number };
    return execError.status ?? 1;
  }
}

describe("issue95 tailwind migration", () => {
  it("test_frontendSrc_searchAppCss_fileAbsentAndNoReferences", () => {
    expect(existsSync(path.join(FRONTEND_SRC, LEGACY_APP_STYLESHEET))).toBe(false);
    expect(collectAppCssReferences(FRONTEND_SRC)).toEqual([]);
  });

  it(
    "test_frontend_npmTestAndBuild_afterMigration_exitZeroWithNoErrors",
    { timeout: 180_000 },
    () => {
      const relativeTestFile = path
        .relative(FRONTEND_ROOT, THIS_FILE)
        .replace(/\\/g, "/");
      const testExitCode = runNpmScript(
        "test",
        ` -- --exclude **/${path.basename(relativeTestFile)}`,
      );
      expect(testExitCode).toBe(0);

      const buildExitCode = runNpmScript("build");
      expect(buildExitCode).toBe(0);
    },
  );
});
