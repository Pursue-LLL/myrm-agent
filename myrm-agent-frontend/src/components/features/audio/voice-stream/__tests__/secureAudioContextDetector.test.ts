/**
 * Secure Audio Context Detector Unit Tests
 */

import { describe, expect, it } from 'vitest';
import {
  detectAudioEnvironment,
  isLanIpAddress,
  resumeAudioContextResiliently,
} from '../secureAudioContextDetector';

describe('secureAudioContextDetector', () => {
  it('should identify LAN IP addresses correctly', () => {
    expect(isLanIpAddress('192.168.1.100')).toBe(true);
    expect(isLanIpAddress('192.168.0.1:3000')).toBe(true);
    expect(isLanIpAddress('10.0.0.5:8080')).toBe(true);
    expect(isLanIpAddress('172.20.10.4')).toBe(true);

    expect(isLanIpAddress('localhost:3000')).toBe(false);
    expect(isLanIpAddress('127.0.0.1:5173')).toBe(false);
    expect(isLanIpAddress('myrm-agent.internal.net')).toBe(false);
  });

  it('should detect secure context for localhost environment', () => {
    const report = detectAudioEnvironment({
      isSecureContext: true,
      protocol: 'http:',
      host: 'localhost:3000',
      hasMediaDevices: true,
      audioContextState: 'running',
    });

    expect(report.isSecureContext).toBe(true);
    expect(report.isLocalhost).toBe(true);
    expect(report.canRecord).toBe(true);
    expect(report.isAutoplaySuspended).toBe(false);
    expect(report.warnings).toHaveLength(0);
  });

  it('should detect insecure LAN HTTP environment and produce downgrade warning and remedy guides', () => {
    const report = detectAudioEnvironment({
      isSecureContext: false,
      protocol: 'http:',
      host: '192.168.31.50:3000',
      hasMediaDevices: false,
      audioContextState: 'suspended',
    });

    expect(report.isSecureContext).toBe(false);
    expect(report.isLanIp).toBe(true);
    expect(report.canRecord).toBe(false);
    expect(report.isAutoplaySuspended).toBe(true);
    expect(report.requiresUserGesture).toBe(true);

    expect(report.warnings.some((w) => w.includes('局域网 HTTP 直连'))).toBe(true);
    expect(report.remedyGuides.some((g) => g.includes('Tailscale'))).toBe(true);
  });

  it('should resume suspended AudioContext resiliently', async () => {
    let resumed = false;
    const fakeAudioCtx = {
      state: 'suspended',
      resume: async () => {
        resumed = true;
      },
    } as unknown as AudioContext;

    const result = await resumeAudioContextResiliently(fakeAudioCtx);
    expect(result.success).toBe(true);
    expect(resumed).toBe(true);
  });
});
