#!/usr/bin/env node
"use strict";

// Launcher shim: locate a suitable Python and run the bundled netlens_mcp
// stdio server. The Python package is copied to ../server/netlens_mcp at
// publish time, so PYTHONPATH points at ../server and we run `python -m netlens_mcp`.

const { execSync, spawn } = require("child_process");
const path = require("path");

const SERVER_DIR = path.join(__dirname, "..", "server");

function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const output = execSync(`${cmd} --version`, {
        encoding: "utf-8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
      const match = output.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major === 3 && minor >= 10) {
          return cmd;
        }
        process.stderr.write(
          `Found Python ${match[1]}.${match[2]} but Python 3.10+ is required.\n`
        );
      }
    } catch {
      // command not found, try next
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  process.stderr.write(
    "Error: Python 3.10+ not found.\n" +
      "NetLens MCP requires Python 3.10 or later.\n" +
      "Install from https://www.python.org/downloads/\n"
  );
  process.exit(1);
}

const args = process.argv.slice(2);
const child = spawn(python, ["-m", "netlens_mcp", ...args], {
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: SERVER_DIR, PYTHONUTF8: "1" },
});

child.on("exit", (code) => process.exit(code ?? 0));
child.on("error", (err) => {
  process.stderr.write(`Error: Failed to start netlens-mcp: ${err.message}\n`);
  process.exit(1);
});
