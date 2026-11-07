/**
 * [INPUT] 无外部依赖（纯函数与常量）
 * [OUTPUT] OPENAPI_DIRECT_TOKEN_BUDGET: OpenAPI 直连注入的 token 预算上限；estimateEndpointTokenLoad: 按端点数估算 schema 的 token 占用
 * [POS] OpenAPI 服务编辑界面的 token 预算估算，预算口径与 harness 的 AGGREGATE_DIRECT_TOKEN_BUDGET 保持一致。
 */

/** Matches harness AGGREGATE_DIRECT_TOKEN_BUDGET (mcp_routing.py). */
export const OPENAPI_DIRECT_TOKEN_BUDGET = 1200;
/** Conservative per-endpoint schema estimate (chars/4 heuristic). */
const ESTIMATED_TOKENS_PER_ENDPOINT = 90;

export function estimateEndpointTokenLoad(endpointCount: number): number {
  return endpointCount * ESTIMATED_TOKENS_PER_ENDPOINT;
}
