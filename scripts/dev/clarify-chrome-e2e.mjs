#!/usr/bin/env bun
/**
 * DEPRECATED — do not run.
 *
 * Spawning MyrmChromeMcp / isolated --user-data-dir Chrome breaks MCP
 * chrome-devtools --autoConnect and opens a blank profile without login.
 *
 * WebUI E2E: use MCP chrome-devtools on your main Chrome (:3000).
 * Enable once: chrome://inspect/#remote-debugging → Allow remote debugging.
 */
console.error(
  'DEPRECATED: clarify-chrome-e2e.mjs removed. Use MCP chrome-devtools --autoConnect on your main Chrome.',
);
process.exit(1);
