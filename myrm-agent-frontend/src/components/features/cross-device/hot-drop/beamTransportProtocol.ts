/**
 * Beam Transport Protocol Utilities
 * 近场无线投送握手、配对码校验与素材载荷验证纯函数引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 纯函数设计，高可测性。
 */

import {
  BeamPayload,
  BeamSessionDescriptor,
  BeamTransportMode,
} from './crossDeviceDropTypes';

export const MAX_BEAM_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25MB

export const ALLOWED_BEAM_MIME_TYPES: readonly string[] = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
  'application/pdf',
];

/**
 * 生成 6 位大写字母与数字组成的易读配对短码
 */
export function generatePairCode(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let i = 0; i < 6; i++) {
    const randomIndex = Math.floor(Math.random() * chars.length);
    code += chars[randomIndex];
  }
  return code;
}

/**
 * 生成频道唯一标识符
 */
export function generateChannelId(): string {
  const randomPart = Math.random().toString(36).substring(2, 10);
  return `beam-${Date.now()}-${randomPart}`;
}

/**
 * 校验待投送文件的类型与体积合规性
 */
export function validateBeamFile(
  fileSizeBytes: number,
  mimeType: string
): { isValid: boolean; errorMessage?: string } {
  if (fileSizeBytes <= 0) {
    return { isValid: false, errorMessage: '文件大小无效（空文件）' };
  }

  if (fileSizeBytes > MAX_BEAM_FILE_SIZE_BYTES) {
    return {
      isValid: false,
      errorMessage: `文件体积超过限制（上限 25MB，当前 ${(
        fileSizeBytes /
        (1024 * 1024)
      ).toFixed(1)}MB）`,
    };
  }

  const isAllowed = ALLOWED_BEAM_MIME_TYPES.some((allowed) => {
    return mimeType.toLowerCase().startsWith(allowed);
  });

  if (!isAllowed) {
    return {
      isValid: false,
      errorMessage: `不支持的文件格式（仅支持 JPG/PNG/WebP/HEIC/PDF，当前为 ${mimeType}）`,
    };
  }

  return { isValid: true };
}

/**
 * 格式化文件体积字节
 */
export function formatByteSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${bytes} B`;
}

/**
 * 创建全新的近场直投会话描述符
 */
export function createBeamSession(
  transportMode: BeamTransportMode = 'webrtc',
  originUrl = 'https://myrm.local'
): BeamSessionDescriptor {
  const channelId = generateChannelId();
  const pairCode = generatePairCode();
  const qrPayloadUrl = `${originUrl}/beam/mobile?channel=${channelId}&pin=${pairCode}`;

  return {
    channelId,
    pairCode,
    qrPayloadUrl,
    transportMode,
    connectedDeviceName: null,
    connectionState: 'idle',
    createdAtTimestamp: Date.now(),
    expiresInSeconds: 300,
  };
}

/**
 * 构造模拟的手机拍摄投送素材载荷
 */
export function createMockBeamPayload(
  deviceName = 'iPhone 16 Pro',
  suggestedPrompt = '请分析这张刚拍摄的白板架构图，并拆解为 Mermaid 格式流程图'
): BeamPayload {
  return {
    id: `payload-${Date.now()}`,
    sourceDeviceName: deviceName,
    fileName: `camera_capture_${Date.now()}.jpg`,
    fileSizeBytes: 1_845_200,
    mimeType: 'image/jpeg',
    dataUrl:
      'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300"><rect width="400" height="300" fill="%231e1e2e"/><text x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" fill="%23a6e3a1" font-family="sans-serif" font-size="16">Whiteboard Capture Mock</text></svg>',
    capturedTimestamp: Date.now(),
    ocrExtractedText: 'Service Gateway -> Auth Filter -> RPC Worker',
    suggestedPrompt,
  };
}
