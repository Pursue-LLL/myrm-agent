/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const agentServiceMock = vi.hoisted(() => ({
  getSaaSPresets: vi.fn(),
  parseOpenAPISpec: vi.fn(),
}));
vi.mock('@/services/agentOpenApi', () => agentServiceMock);
vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));

import { AgentOpenAPIServicesTab } from '../AgentOpenAPIServicesTab';

beforeEach(() => {
  agentServiceMock.getSaaSPresets.mockReset();
});

describe('AgentOpenAPIServicesTab preset picker copy', () => {
  it('shows the translated loading text while presets are being fetched', async () => {
    agentServiceMock.getSaaSPresets.mockReturnValue(new Promise(() => undefined));
    render(<AgentOpenAPIServicesTab services={[]} onChange={() => undefined} />);

    await userEvent.click(screen.getByText('addFromPreset'));

    expect(screen.getByText('presetsLoading')).toBeInTheDocument();
  });

  it('shows the translated empty text when no preset is available', async () => {
    agentServiceMock.getSaaSPresets.mockResolvedValue([]);
    render(<AgentOpenAPIServicesTab services={[]} onChange={() => undefined} />);

    await userEvent.click(screen.getByText('addFromPreset'));

    expect(await screen.findByText('presetsEmpty')).toBeInTheDocument();
  });

  it('labels the enable button of each preset and applies it on click', async () => {
    agentServiceMock.getSaaSPresets.mockResolvedValue([
      {
        name: 'GitHub Issues',
        description: 'Manage issues',
        spec_url: 'https://example.com/spec.json',
        auth_type: 'bearer',
        selected_endpoints: [],
      },
    ]);
    const onChange = vi.fn();
    render(<AgentOpenAPIServicesTab services={[]} onChange={onChange} />);

    await userEvent.click(screen.getByText('addFromPreset'));
    await userEvent.click(await screen.findByText('presetEnable'));

    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ name: 'github_issues', enabled: true })]);
  });
});
