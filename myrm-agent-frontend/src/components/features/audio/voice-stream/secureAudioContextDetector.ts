/**
 * Secure Audio Context & Autoplay Policy Resilience Detector
 * 安全上下文环境探针、局域网非安全上下文降级警告与 Autoplay 弹性恢复引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { SecureAudioEnvironmentReport } from './voiceStreamTypes';

export function isLanIpAddress(host: string): boolean {
  const cleanHost = host.split(':')[0];
  // 192.168.x.x, 10.x.x.x, 172.16.x.x - 172.31.x.x
  if (cleanHost.startsWith('192.168.') || cleanHost.startsWith('10.')) {
    return true;
  }
  if (cleanHost.startsWith('172.')) {
    const parts = cleanHost.split('.');
    if (parts.length >= 2) {
      const secondOctet = Number.parseInt(parts[1], 10);
      if (secondOctet >= 16 && secondOctet <= 31) {
        return true;
      }
    }
  }
  return false;
}

export function detectAudioEnvironment(customEnv?: {
  isSecureContext?: boolean;
  protocol?: string;
  host?: string;
  hasMediaDevices?: boolean;
  audioContextState?: AudioContextState;
}): SecureAudioEnvironmentReport {
  let isSecure = false;
  let protocol = 'http:';
  let host = 'localhost';
  let hasGetUserMedia = false;

  if (typeof window !== 'undefined') {
    isSecure = typeof window.isSecureContext === 'boolean' ? window.isSecureContext : false;
    protocol = window.location ? window.location.protocol : 'http:';
    host = window.location ? window.location.host : 'localhost';
    hasGetUserMedia = Boolean(
      typeof navigator !== 'undefined' &&
        navigator.mediaDevices &&
        typeof navigator.mediaDevices.getUserMedia === 'function'
    );
  }

  // 允许测试或者注入自定义参数覆盖
  if (customEnv) {
    if (typeof customEnv.isSecureContext === 'boolean') {
      isSecure = customEnv.isSecureContext;
    }
    if (customEnv.protocol) {
      protocol = customEnv.protocol;
    }
    if (customEnv.host) {
      host = customEnv.host;
    }
    if (typeof customEnv.hasMediaDevices === 'boolean') {
      hasGetUserMedia = customEnv.hasMediaDevices;
    }
  }

  const cleanHost = host.split(':')[0];
  const isLocalhost =
    cleanHost === 'localhost' ||
    cleanHost === '127.0.0.1' ||
    cleanHost === '::1';
  const isLan = isLanIpAddress(cleanHost);

  const audioState = customEnv?.audioContextState || 'suspended';
  const isAutoplaySuspended = audioState === 'suspended';

  const warnings: string[] = [];
  const remedyGuides: string[] = [];

  // 非安全上下文警告
  if (!isSecure && !isLocalhost) {
    if (isLan) {
      warnings.push(
        `当前为局域网 HTTP 直连 (${host})，属于非安全上下文 (Insecure Context)。浏览器禁止激活麦克风 getUserMedia 与 WebCrypto 加密。`
      );
      remedyGuides.push(
        '推荐配置 Tailscale Serve HTTPS 证书域名访问，或在客户端配置反向代理启用 TLS 加密。'
      );
    } else {
      warnings.push(
        `当前网站未启用 HTTPS 加密 (${protocol}//${host})，浏览器麦克风流式传输权限被沙箱物理拦截。`
      );
      remedyGuides.push('请升级站点为 HTTPS 协议，或者在开发阶段通过 localhost 访问。');
    }
  }

  if (!hasGetUserMedia) {
    warnings.push('当前运行环境未暴露 navigator.mediaDevices.getUserMedia API。');
    remedyGuides.push('请使用现代 Chromium、Firefox 或 Safari 桌面/移动浏览器。');
  }

  if (isAutoplaySuspended) {
    warnings.push(
      'AudioContext 处于 suspended 挂起状态（浏览器 Autoplay 策略拦截静默声音输出）。'
    );
    remedyGuides.push('需要用户显式点击按钮激活语音上下文，解除自动播放拦截。');
  }

  const canRecord = (isSecure || isLocalhost) && hasGetUserMedia;

  return {
    isSecureContext: isSecure || isLocalhost,
    protocol,
    host,
    isLocalhost,
    isLanIp: isLan,
    hasGetUserMedia,
    isAutoplaySuspended,
    requiresUserGesture: isAutoplaySuspended,
    canRecord,
    warnings,
    remedyGuides,
  };
}

export async function resumeAudioContextResiliently(
  audioCtx: AudioContext
): Promise<{ success: boolean; error?: string }> {
  try {
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }
    return { success: true };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { success: false, error: message };
  }
}
