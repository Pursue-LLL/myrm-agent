import type { PluginDiagnostic } from './pluginImportTypes';

/**
 * The preview rows already explain these in the user's language (missing-file note, privilege warning),
 * so the header must not repeat them as an English sentence.
 */
const ROW_LEVEL_CODES: ReadonlySet<string> = new Set(['mcp_missing_artifact', 'capability_undeclared_privilege']);

export const UNDECLARED_PRIVILEGE_CODE = 'capability_undeclared_privilege';

export type DiagnosticMessageKey =
  | 'unsupportedFormat'
  | 'manifestInvalid'
  | 'serversInvalid'
  | 'skillSkipped'
  | 'serverSkipped'
  | 'filesIgnored'
  | 'generic';

export type DiagnosticScope = 'plugin' | 'skill' | 'servers' | 'server';

/**
 * Maps the backend's stable diagnostic code to the sentence the user reads. The backend's English
 * `message` stays a console diagnostic; a code this client does not know still gets a sentence.
 */
export function diagnosticMessageKey(code: string): DiagnosticMessageKey {
  switch (code) {
    case 'unsupported_schema':
    case 'manifest_missing':
    case 'manifest_invalid_json':
      return 'unsupportedFormat';
    case 'skill_invalid':
      return 'skillSkipped';
    case 'mcp_invalid_server':
      return 'serverSkipped';
    case 'files_ignored':
      return 'filesIgnored';
    default:
      if (code.startsWith('manifest_')) {
        return 'manifestInvalid';
      }
      if (code.startsWith('mcp_')) {
        return 'serversInvalid';
      }
      return 'generic';
  }
}

/** `skill:<name>` / `mcp:<name>` / `mcp` / `plugin` → what the diagnostic is about, with the name when it has one. */
export function diagnosticScope(component: string): { scope: DiagnosticScope; name: string } {
  const separator = component.indexOf(':');
  const kind = separator < 0 ? component : component.slice(0, separator);
  const name = separator < 0 ? '' : component.slice(separator + 1);
  if (kind === 'skill' && name) {
    return { scope: 'skill', name };
  }
  if (kind === 'mcp') {
    return name ? { scope: 'server', name } : { scope: 'servers', name: '' };
  }
  return { scope: 'plugin', name: '' };
}

export function headerDiagnostics(diagnostics: PluginDiagnostic[]): PluginDiagnostic[] {
  return diagnostics.filter((diagnostic) => !ROW_LEVEL_CODES.has(diagnostic.code));
}
