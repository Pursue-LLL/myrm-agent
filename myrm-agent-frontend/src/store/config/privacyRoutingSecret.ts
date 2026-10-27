/**
 * [INPUT]
 * @/services/config::getConfigSyncManager (POS: 配置同步管理器)
 * @/services/config/types::PrivacyRoutingConfig, PrivacyRoutingSecretConfigValue (POS: 路由偏好与本地模型密钥的配置类型)
 *
 * [OUTPUT]
 * PrivacyRoutingRequest: 随聊天请求发送的路由配置（路由偏好 + 本地模型密钥）
 * readPrivacyRoutingSecret / writePrivacyRoutingSecret: 本地模型密钥的同步读写
 * loadPrivacyRoutingSecret: 渐进加载下先确保该行已同步再读取（后端没有这一行或没取到时，短时间内不重复请求）
 * buildPrivacyRoutingRequest: 发送时把密钥并入路由偏好，没有本地模型则不发送路由
 *
 * [POS]
 * 本地模型端点密钥的唯一读写入口。密钥不放进 personalSettings（该行明文存放，并被审计历史与默认导出带走），
 * 而是存进服务端加密的 privacyRoutingSecret 行；只在发送请求这一刻与路由偏好合成一次，不进入 Zustand 状态。
 */
import { getConfigSyncManager } from '@/services/config';
import type { PrivacyRoutingConfig } from '@/services/config/types';

export type PrivacyRoutingRequest = PrivacyRoutingConfig & { localApiKey?: string };

const SECRET_ROW = 'privacyRoutingSecret';
/** 后端没有这一行（从未保存过密钥）或这次没取到时，隔多久再问一次；有行之后命中缓存，不再请求。 */
const MISSING_ROW_RECHECK_MS = 10_000;

let pendingLoad: Promise<void> | null = null;
let missingRowCheckedAt = Number.NEGATIVE_INFINITY;

export function readPrivacyRoutingSecret(): string {
  return getConfigSyncManager().get(SECRET_ROW)?.localApiKey ?? '';
}

export function writePrivacyRoutingSecret(localApiKey: string): void {
  getConfigSyncManager().set(SECRET_ROW, { localApiKey });
}

async function ensureRowLoaded(): Promise<void> {
  const manager = getConfigSyncManager();
  if (manager.get(SECRET_ROW) !== null || Date.now() - missingRowCheckedAt < MISSING_ROW_RECHECK_MS) {
    return;
  }
  pendingLoad ??= manager.ensureKeyLoaded(SECRET_ROW).finally(() => {
    pendingLoad = null;
    if (manager.get(SECRET_ROW) === null) {
      missingRowCheckedAt = Date.now();
    }
  });
  await pendingLoad;
}

/**
 * 渐进加载下该行在后台预加载；读取即决策的路径（发送请求）必须先等它就绪，否则会漏掉已保存的密钥。
 * 从未保存过密钥的用户没有这一行，`ensureKeyLoaded` 对缺失的行每次都会再请求，所以缺失时按时间窗口去重；
 * 同时到达的调用共用一次请求。同步失败不阻断调用方：返回缓存里已有的值（没有则为空），窗口过后再试。
 */
export async function loadPrivacyRoutingSecret(): Promise<string> {
  try {
    await ensureRowLoaded();
  } catch (error) {
    console.warn('[privacyRoutingSecret] the key row could not be loaded:', error);
  }
  return readPrivacyRoutingSecret();
}

export async function buildPrivacyRoutingRequest(
  routing: PrivacyRoutingConfig | undefined,
): Promise<PrivacyRoutingRequest | undefined> {
  if (!routing?.localModel) {
    return undefined;
  }
  const localApiKey = await loadPrivacyRoutingSecret();
  return localApiKey ? { ...routing, localApiKey } : routing;
}
