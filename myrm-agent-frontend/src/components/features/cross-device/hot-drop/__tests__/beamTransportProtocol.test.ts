import { describe, it, expect } from 'vitest';
import {
  generatePairCode,
  generateChannelId,
  validateBeamFile,
  formatByteSize,
  createBeamSession,
  createMockBeamPayload,
  MAX_BEAM_FILE_SIZE_BYTES,
} from '../beamTransportProtocol';

describe('beamTransportProtocol', () => {
  it('正确生成 6 位易读配对短码且不包含易混淆字符', () => {
    const code = generatePairCode();
    expect(code).toHaveLength(6);
    expect(code).toMatch(/^[A-Z0-9]{6}$/);
    expect(code).not.toContain('O');
    expect(code).not.toContain('I');
    expect(code).not.toContain('0');
    expect(code).not.toContain('1');
  });

  it('正确生成频道唯一标识符', () => {
    const channelId = generateChannelId();
    expect(channelId).toMatch(/^beam-\d+-[a-z0-9]+$/);
  });

  it('正确校验文件体积与 MIME 类型合规性', () => {
    // 正常图片
    expect(validateBeamFile(1024 * 500, 'image/png').isValid).toBe(true);
    expect(validateBeamFile(1024 * 1024, 'image/jpeg').isValid).toBe(true);
    expect(validateBeamFile(1024 * 800, 'application/pdf').isValid).toBe(true);

    // 空文件
    expect(validateBeamFile(0, 'image/png').isValid).toBe(false);

    // 超限文件 (> 25MB)
    const tooLarge = validateBeamFile(
      MAX_BEAM_FILE_SIZE_BYTES + 1024,
      'image/jpeg'
    );
    expect(tooLarge.isValid).toBe(false);
    expect(tooLarge.errorMessage).toContain('文件体积超过限制');

    // 不支持的文件格式
    const unsupported = validateBeamFile(1024 * 100, 'video/mp4');
    expect(unsupported.isValid).toBe(false);
    expect(unsupported.errorMessage).toContain('不支持的文件格式');
  });

  it('正确格式化文件大小字节', () => {
    expect(formatByteSize(2 * 1024 * 1024)).toBe('2.00 MB');
    expect(formatByteSize(512 * 1024)).toBe('512.0 KB');
    expect(formatByteSize(850)).toBe('850 B');
  });

  it('创建全新的近场直投会话描述符', () => {
    const session = createBeamSession('webrtc', 'https://agent.local');
    expect(session.transportMode).toBe('webrtc');
    expect(session.connectionState).toBe('idle');
    expect(session.qrPayloadUrl).toContain('https://agent.local/beam/mobile');
    expect(session.pairCode).toHaveLength(6);
    expect(session.expiresInSeconds).toBe(300);
  });

  it('构造模拟的手机拍摄投送素材载荷', () => {
    const payload = createMockBeamPayload('Xiaomi 14 Ultra', '总结白板');
    expect(payload.sourceDeviceName).toBe('Xiaomi 14 Ultra');
    expect(payload.suggestedPrompt).toBe('总结白板');
    expect(payload.mimeType).toBe('image/jpeg');
    expect(payload.ocrExtractedText).toBeDefined();
  });
});
