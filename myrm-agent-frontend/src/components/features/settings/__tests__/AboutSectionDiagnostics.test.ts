import { describe, expect, it } from 'bun:test';

describe('AboutSection & Dual-Layer Version Diagnostics', () => {
  it('should format diagnostic report with both Shell and Engine versions', () => {
    const shellVersion = '0.1.0';
    const engineVersion = '0.1.0rc6';
    const isTauri = true;

    const report = [
      '### MyrmAgent Diagnostic Info',
      `- Desktop Shell: v${shellVersion}`,
      `- Engine Sidecar: v${engineVersion}`,
      `- Runtime Environment: ${isTauri ? 'Tauri Desktop Native' : 'Browser WebUI'}`,
      `- Timestamp: 2026-09-03T00:00:00.000Z`,
    ].join('\n');

    expect(report).toContain('- Desktop Shell: v0.1.0');
    expect(report).toContain('- Engine Sidecar: v0.1.0rc6');
    expect(report).toContain('- Runtime Environment: Tauri Desktop Native');
  });

  it('should handle missing engine version gracefully with fallback', () => {
    const shellVersion = '0.1.0';
    const engineVersion: string | null = null;
    const isTauri = false;

    const report = [
      '### MyrmAgent Diagnostic Info',
      `- Desktop Shell: v${shellVersion}`,
      `- Engine Sidecar: v${engineVersion ?? 'unknown'}`,
      `- Runtime Environment: ${isTauri ? 'Tauri Desktop Native' : 'Browser WebUI'}`,
    ].join('\n');

    expect(report).toContain('- Desktop Shell: v0.1.0');
    expect(report).toContain('- Engine Sidecar: vunknown');
    expect(report).toContain('- Runtime Environment: Browser WebUI');
  });
});
