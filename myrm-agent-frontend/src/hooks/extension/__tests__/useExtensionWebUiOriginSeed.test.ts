import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useExtensionWebUiOriginSeed } from '@/hooks/extension/useExtensionWebUiOriginSeed';
import {
  getExtensionClipAgentConfig,
  updateExtensionClipAgentConfig,
} from '@/services/extension';

vi.mock('@/services/extension', () => ({
  getExtensionClipAgentConfig: vi.fn(),
  updateExtensionClipAgentConfig: vi.fn(),
}));

describe('useExtensionWebUiOriginSeed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getExtensionClipAgentConfig).mockResolvedValue({
      agent_id: 'agent-1',
      web_ui_origin: null,
    });
    vi.mocked(updateExtensionClipAgentConfig).mockResolvedValue({
      agent_id: 'agent-1',
      web_ui_origin: 'http://localhost:3000',
    });
  });

  it('seeds web_ui_origin once when origin differs', async () => {
    renderHook(() => useExtensionWebUiOriginSeed());

    await waitFor(() => {
      expect(updateExtensionClipAgentConfig).toHaveBeenCalledWith(
        'agent-1',
        'http://localhost:3000',
      );
    });
  });

  it('skips PUT when origin already matches', async () => {
    vi.mocked(getExtensionClipAgentConfig).mockResolvedValue({
      agent_id: 'agent-1',
      web_ui_origin: 'http://localhost:3000',
    });

    renderHook(() => useExtensionWebUiOriginSeed());

    await waitFor(() => {
      expect(getExtensionClipAgentConfig).toHaveBeenCalled();
    });
    expect(updateExtensionClipAgentConfig).not.toHaveBeenCalled();
  });
});
