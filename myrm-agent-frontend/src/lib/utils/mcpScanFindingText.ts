import type { MCPScanFinding } from '@/store/config/types';

type SettingsTranslate = (
  key: string,
  values?: Record<string, string | number | Date>,
) => string;

function localizedOrFallback(t: SettingsTranslate, key: string, fallback: string): string {
  const translated = t(key);
  return translated === key ? fallback : translated;
}

export function getMcpFindingDescription(finding: MCPScanFinding, t: SettingsTranslate): string {
  return localizedOrFallback(t, `mcpThreat.${finding.threatType}`, finding.description);
}

export function getMcpFindingRecommendation(
  finding: MCPScanFinding,
  t: SettingsTranslate,
): string | undefined {
  if (!finding.recommendation) {
    return undefined;
  }
  return localizedOrFallback(t, `mcpThreatRec.${finding.threatType}`, finding.recommendation);
}

export function formatMcpFindingWithField(finding: MCPScanFinding, t: SettingsTranslate): string {
  return `${getMcpFindingDescription(finding, t)} (${finding.field})`;
}

interface McpFindingDetailPayload {
  threatType?: string;
  severity?: string;
  description?: string;
  recommendation?: string;
}

export function parseMcpFindingsFromApiErrorDetails(
  details: Array<{ field?: string; issue: string }>,
): MCPScanFinding[] {
  const findings: MCPScanFinding[] = [];
  for (const detail of details) {
    try {
      const parsed = JSON.parse(detail.issue) as McpFindingDetailPayload;
      if (!parsed.threatType || !parsed.description) {
        continue;
      }
      findings.push({
        threatType: parsed.threatType,
        severity: parsed.severity ?? 'high',
        description: parsed.description,
        field: detail.field ?? '',
        recommendation: parsed.recommendation,
      });
    } catch {
      continue;
    }
  }
  return findings;
}

export function formatMcpGateBlockedMessage(
  options: {
    verifyError?: string;
    verifyFindings?: MCPScanFinding[];
    staticFindings?: MCPScanFinding[];
    fallback: string;
  },
  t: SettingsTranslate,
): string {
  const finding = options.verifyFindings?.[0] ?? options.staticFindings?.[0];
  if (finding) {
    return formatMcpFindingWithField(finding, t);
  }
  return options.verifyError || options.fallback;
}
