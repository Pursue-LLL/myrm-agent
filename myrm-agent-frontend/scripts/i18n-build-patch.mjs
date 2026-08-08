#!/usr/bin/env node
/**
 * [INPUT] flat JSON: { "dotted.key": "translation", ... } 或 [{ key, de }]
 * [OUTPUT] nested locale patch tree (stdout 或 --out)
 * [POS] translation-patches 嵌套补丁构建器，供 dump→translate→patch-apply 工作流使用。
 *
 * Usage:
 *   node scripts/i18n-build-patch.mjs translations-flat.json --out scripts/translation-patches/de/batch-NN.json
 */

import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const inputPath = process.argv[2];
if (!inputPath) {
  console.error('用法: node scripts/i18n-build-patch.mjs <flat.json> [--out FILE]');
  process.exit(1);
}

const outIdx = process.argv.indexOf('--out');
const outFile = outIdx >= 0 ? process.argv[outIdx + 1] : undefined;

const raw = JSON.parse(readFileSync(resolve(inputPath), 'utf-8'));
/** @type {Record<string, string>} */
const flat = Array.isArray(raw)
  ? Object.fromEntries(raw.map(({ key, de, translation }) => [key, de ?? translation]))
  : raw;

function setNested(root, dottedPath, value) {
  const parts = dottedPath.split('.');
  let node = root;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const part = parts[i];
    if (typeof node[part] !== 'object' || node[part] === null || Array.isArray(node[part])) {
      node[part] = {};
    }
    node = node[part];
  }
  node[parts[parts.length - 1]] = value;
}

const patch = {};
for (const [key, value] of Object.entries(flat)) {
  setNested(patch, key, value);
}

const payload = `${JSON.stringify(patch, null, 2)}\n`;
if (outFile) writeFileSync(resolve(outFile), payload);
else process.stdout.write(payload);
