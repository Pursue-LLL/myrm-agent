/**
 * [INPUT]
 * - services/llm-config::scanMCPConfig, scanMCPConfigBatch, validateMCPConfig (POS: MCP REST clients)
 * - store/config/types::MCPServiceConfig, MCPLastScanSummary (POS: MCP config DTOs)
 *
 * [OUTPUT]
 * - gateMcpConfig, gateMcpConfigBatch, gateMcpEnable, mcpConfigHasSecretRefs, buildLastScanSummary
 *
 * [POS]
 * Unified MCP security gate for Settings UI save, enable, import, and catalog flows.
 */

import {
  scanMCPConfig,
  scanMCPConfigBatch,
  validateMCPConfig,
  type MCPScanResult,
} from '@/services/llm-config';
import type { MCPLastScanSummary, MCPScanFinding, MCPServiceConfig } from '@/store/config/types';

export interface McpGateResult {
  allowed: boolean;
  scanResult: MCPScanResult;
  needsAcknowledgement: boolean;
  verifyError?: string;
  verifyFindings?: MCPScanFinding[];
  verifyLatency?: number;
  instructions?: string;
}

export interface McpBatchGateResult {
  blocked: MCPServiceConfig | null;
  scanResults: MCPScanResult[];
  needsAcknowledgement: { config: MCPServiceConfig; scanResult: MCPScanResult } | null;
}

export function buildLastScanSummary(scanResult: MCPScanResult): MCPLastScanSummary {
  return {
    maxSeverity: scanResult.maxSeverity,
    scannedAt: Date.now(),
    findingCount: scanResult.findings.length,
  };
}

export function mcpConfigHasSecretRefs(config: MCPServiceConfig): boolean {
  return Object.values(config.headers || {}).some((value) => value.includes('{{secret:'));
}

/** Enable/save gate: static scan + verify when headers have no unresolved secret refs. */
export async function gateMcpEnable(
  config: MCPServiceConfig,
  options?: {
    acknowledgedHighRisks?: boolean;
  },
): Promise<McpGateResult> {
  return gateMcpConfig(config, {
    acknowledgedHighRisks: options?.acknowledgedHighRisks,
    runVerify: !mcpConfigHasSecretRefs(config),
  });
}

export async function gateMcpConfig(
  config: MCPServiceConfig,
  options?: {
    acknowledgedHighRisks?: boolean;
    runVerify?: boolean;
  },
): Promise<McpGateResult> {
  const scanResult = await scanMCPConfig(config);
  if (!scanResult.allowSave) {
    return { allowed: false, scanResult, needsAcknowledgement: false };
  }
  if (scanResult.requiresAcknowledgement && !options?.acknowledgedHighRisks) {
    return { allowed: false, scanResult, needsAcknowledgement: true };
  }
  if (options?.runVerify) {
    const verifyResult = await validateMCPConfig(config, options.acknowledgedHighRisks);
    if (!verifyResult.success) {
      return {
        allowed: false,
        scanResult,
        needsAcknowledgement: false,
        verifyError: verifyResult.message,
        verifyFindings: verifyResult.scanFindings,
      };
    }
    return {
      allowed: true,
      scanResult,
      needsAcknowledgement: false,
      verifyLatency: verifyResult.latency,
      instructions: verifyResult.instructions,
    };
  }
  return { allowed: true, scanResult, needsAcknowledgement: false };
}

export async function gateMcpConfigBatch(
  configs: MCPServiceConfig[],
  acknowledgedHighRisks = false,
): Promise<McpBatchGateResult> {
  if (configs.length === 0) {
    return { blocked: null, scanResults: [], needsAcknowledgement: null };
  }

  const scanResults =
    configs.length === 1
      ? [await scanMCPConfig(configs[0])]
      : (await scanMCPConfigBatch(configs)).results;

  for (let i = 0; i < configs.length; i += 1) {
    const scanResult = scanResults[i];
    if (scanResult && !scanResult.allowSave) {
      return { blocked: configs[i], scanResults, needsAcknowledgement: null };
    }
  }

  if (!acknowledgedHighRisks) {
    for (let i = 0; i < configs.length; i += 1) {
      const scanResult = scanResults[i];
      if (scanResult?.requiresAcknowledgement) {
        return {
          blocked: null,
          scanResults,
          needsAcknowledgement: { config: configs[i], scanResult },
        };
      }
    }
  }

  return { blocked: null, scanResults, needsAcknowledgement: null };
}
