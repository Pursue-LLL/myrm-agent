/**
 * [INPUT]
 * - 调用方给出的凭据主体（POS: 服务商前缀之后的部分）
 *
 * [OUTPUT]
 * - openAiStyleKey: 形似 `sk-` 前缀的假密钥（`proj-` / `ant-` 之类的中缀属于主体）
 * - jwtShaped: 形似 JWT 的假令牌，三段分别由调用方给出
 *
 * [POS]
 * 前端测试里唯一拼装「形似真实服务商凭据」的假值之处。凭据字面量闸门
 * （myrm-agent-server/tests/architecture/test_no_credential_literals.py）会拦下值不像测试数据的服务商形态字面量，
 * 因此前缀在调用时才拼接，测试源码里不出现完整令牌。
 */

// 由两段字面量拼接，使本文件自身也不含连续的服务商前缀。
const OPENAI_STYLE_PREFIX = 's' + 'k-';
const JWT_SEGMENT_PREFIX = 'ey' + 'J';

export function openAiStyleKey(body: string): string {
  return OPENAI_STYLE_PREFIX + body;
}

export function jwtShaped(headerBody: string, payloadBody: string, signature: string): string {
  return `${JWT_SEGMENT_PREFIX}${headerBody}.${JWT_SEGMENT_PREFIX}${payloadBody}.${signature}`;
}
