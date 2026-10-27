/**
 * [INPUT]
 * @/services/config::getConfigSyncManager (POS: 配置同步管理器)
 * @/services/config/types::PrivacyRoutingConfig, PrivacyRoutingSecretConfigValue (POS: 路由偏好与本地模型密钥的配置类型)
 *
 * [OUTPUT]
 * PrivacyRoutingRequest: 随聊天请求发送的路由配置（路由偏好 + 本地模型密钥）
 * readPrivacyRoutingSecret / writePrivacyRoutingSecret: 本地模型密钥的同步读写
 * loadPrivacyRoutingSecret: 渐进加载下先确保该行已同步再读取（每个页面会话只向后端请求一次）
 * buildPrivacyRoutingRequest: 发送时把密钥并入路由偏好，没有本地模型则不发送路由
 *
 * [POS]
 * 本地模型端点密钥的唯一读写入口。密钥不放进 personalSettings（该行明文存放，并被审计历史与默认导出带走），
 * 而是存进服务端加密的 privacyRoutingSecret 行；只在发送请求这一刻与路由偏好合成一次，不进入 Zustand 状态。
 */
import { getConfigSyncManager } from '@/services/config';
import type { PrivacyRoutingConfig } from '@/services/config/types';

export type PrivacyRoutingRequest = PrivacyRoutingConfig & { localApiKey?: string };

let rowLoad: Promise<void> | null = null;

export function readPrivacyRoutingSecret(): string {
  return getConfigSyncManager().get('privacyRoutingSecret')?.localApiKey ?? '';
}

export function writePrivacyRoutingSecret(localApiKey: string): void {
  getConfigSyncManager().set('privacyRoutingSecret', { localApiKey });
}

/**
 * 渐进加载下该行在后台预加载；读取即决策的路径（发送请求）必须先等它就绪，否则会漏掉已保存的密钥。
 * 从未保存过密钥的用户没有这一行，`ensureKeyLoaded` 每次都会再请求一次，所以这里只等一次。
 */
export async function loadPrivacyRoutingSecret(): Promise<string> {
  rowLoad ??= getConfigSyncManager().ensureKeyLoaded('privacyRoutingSecret');
  await rowLoad;
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
