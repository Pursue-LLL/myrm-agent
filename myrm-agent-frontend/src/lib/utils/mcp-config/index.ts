/**
 * [POS]
 * MCP-config domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export {
  canonicalizeMCPTransport,
  normalizeMCPKeepaliveInterval,
  normalizeMCPServiceConfig,
  normalizeMCPServiceConfigs,
} from './mcpConfigNormalizer';
export { parseMCPConfigsFromJSON, parseServerConfig } from './mcpConfigParser';
export {
  formatMcpFindingWithField,
  formatMcpGateBlockedMessage,
  getMcpFindingDescription,
  getMcpFindingRecommendation,
  parseMcpFindingsFromApiErrorDetails,
} from './mcpScanFindingText';
