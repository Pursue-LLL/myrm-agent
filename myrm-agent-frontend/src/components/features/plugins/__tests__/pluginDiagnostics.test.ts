/**
 * [INPUT]
 * pluginDiagnostics.ts, locales/{zh,en,zh-TW,ja,de,ko}.json — settings.plugins.import.diagnostics
 * [OUTPUT]
 * Vitest: every diagnostic code maps to a sentence that exists in every locale.
 * [POS]
 * Guards the code → localized sentence contract of the plugin import preview.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  diagnosticMessageKey,
  diagnosticScope,
  headerDiagnostics,
  type DiagnosticMessageKey,
} from '../pluginDiagnostics';

const LOCALES_ROOT = resolve(process.cwd(), 'locales');
const LANGUAGES = ['zh', 'en', 'zh-TW', 'ja', 'de', 'ko'] as const;
const MESSAGE_KEYS: DiagnosticMessageKey[] = [
  'unsupportedFormat',
  'manifestInvalid',
  'serversInvalid',
  'skillSkipped',
  'serverSkipped',
  'filesIgnored',
  'generic',
];
const SCOPE_KEYS = ['plugin', 'skill', 'servers', 'server'] as const;

// Every code the harness plugin parser emits for a package the user is importing.
const HARNESS_CODES: Record<string, DiagnosticMessageKey> = {
  unsupported_schema: 'unsupportedFormat',
  manifest_missing: 'unsupportedFormat',
  manifest_invalid_json: 'unsupportedFormat',
  manifest_invalid_name: 'manifestInvalid',
  manifest_invalid_extension: 'manifestInvalid',
  manifest_invalid_capability: 'manifestInvalid',
  manifest_invalid_author: 'manifestInvalid',
  manifest_invalid_field: 'manifestInvalid',
  mcp_missing: 'serversInvalid',
  mcp_invalid_json: 'serversInvalid',
  mcp_invalid_root: 'serversInvalid',
  mcp_unsupported_schema: 'serversInvalid',
  mcp_version_mismatch: 'serversInvalid',
  mcp_unknown_field: 'serversInvalid',
  mcp_invalid_servers: 'serversInvalid',
  mcp_invalid_config: 'serversInvalid',
  mcp_invalid_server: 'serverSkipped',
  skill_invalid: 'skillSkipped',
  files_ignored: 'filesIgnored',
  a_code_from_a_newer_backend: 'generic',
};

interface DiagnosticsCopy {
  scope: Record<string, string>;
  messages: Record<string, string>;
}

function copyOf(language: string): DiagnosticsCopy {
  const bundle = JSON.parse(readFileSync(resolve(LOCALES_ROOT, `${language}.json`), 'utf-8')) as {
    settings: { plugins: { import: { diagnostics: DiagnosticsCopy } } };
  };
  return bundle.settings.plugins.import.diagnostics;
}

describe('diagnosticMessageKey', () => {
  it.each(Object.entries(HARNESS_CODES))('%s → %s', (code, key) => {
    expect(diagnosticMessageKey(code)).toBe(key);
  });
});

describe('diagnosticScope', () => {
  it.each([
    ['plugin', 'plugin', ''],
    ['skill:extract', 'skill', 'extract'],
    ['mcp', 'servers', ''],
    ['mcp:pdf-server', 'server', 'pdf-server'],
    ['mcp:a:b', 'server', 'a:b'],
    ['skill:', 'plugin', ''],
    ['something_new', 'plugin', ''],
  ])('%s', (component, scope, name) => {
    expect(diagnosticScope(component)).toEqual({ scope, name });
  });
});

describe('headerDiagnostics', () => {
  it('drops what a preview row already explains', () => {
    const diagnostics = [
      { component: 'plugin', code: 'files_ignored', message: 'm', level: 'info' },
      { component: 'mcp:x', code: 'mcp_missing_artifact', message: 'm', level: 'error' },
      { component: 'mcp:x', code: 'capability_undeclared_privilege', message: 'm', level: 'error' },
    ];
    expect(headerDiagnostics(diagnostics).map((d) => d.code)).toEqual(['files_ignored']);
  });
});

describe.each(LANGUAGES)('%s locale', (language) => {
  it('has a sentence for every message and scope key', () => {
    const copy = copyOf(language);
    for (const key of MESSAGE_KEYS) {
      expect(copy.messages[key]?.trim(), key).toBeTruthy();
    }
    for (const key of SCOPE_KEYS) {
      expect(copy.scope[key]?.trim(), key).toBeTruthy();
    }
    expect(Object.keys(copy.messages).sort()).toEqual([...MESSAGE_KEYS].sort());
    expect(Object.keys(copy.scope).sort()).toEqual([...SCOPE_KEYS].sort());
  });

  it('names the skill or server in the scopes that carry a name', () => {
    const { scope } = copyOf(language);
    expect(scope.skill).toContain('{name}');
    expect(scope.server).toContain('{name}');
  });

  it('keeps technical wording out of user-facing sentences', () => {
    const { messages } = copyOf(language);
    for (const text of Object.values(messages)) {
      expect(text).not.toMatch(/\$schema|plugin\.json|mcp\.json|manifest/i);
    }
  });
});
