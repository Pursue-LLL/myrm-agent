/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { PersonalityCatalogItem } from '@/services/agent';

const mockGetPersonalityCatalog = vi.fn();
let mockLocale = 'en';

const stableT = Object.assign((key: string) => key, { has: () => true });

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => mockLocale,
}));

vi.mock('@/services/agent', () => ({
  getPersonalityCatalog: () => mockGetPersonalityCatalog(),
}));

import { PersonalityStylePicker } from '../PersonalityStylePicker';

const CATALOG: PersonalityCatalogItem[] = [
  {
    id: 'professional',
    displayName: 'Professional',
    displayNameZh: '专业模式',
    description: 'Default professional assistant style',
    descriptionZh: '默认专业助手风格',
    exampleResponse: 'Here is a structured approach...',
    exampleResponseZh: '下面是分步骤的处理方案。',
    iconId: 'briefcase',
    category: 'practical',
  },
  {
    id: 'concise',
    displayName: 'Concise',
    displayNameZh: '简洁模式',
    description: 'Direct and to-the-point responses',
    descriptionZh: '极致简洁，高信息密度',
    exampleResponse: 'Wrap it in useMemo.',
    exampleResponseZh: '用 useMemo 包住这个属性即可。',
    iconId: 'zap',
    category: 'practical',
  },
  {
    id: 'zen-custom',
    displayName: 'Zen Custom',
    displayNameZh: '禅意自定义',
    description: 'Calm custom preset served by the catalog',
    descriptionZh: '由目录下发的自定义风格',
    exampleResponse: 'Breathe. Then fix the failing test.',
    exampleResponseZh: '先深呼吸，再修好失败的测试。',
    iconId: 'unknown-icon',
    category: 'fun',
  },
];

describe('PersonalityStylePicker', () => {
  beforeEach(() => {
    mockLocale = 'en';
    mockGetPersonalityCatalog.mockReset();
    mockGetPersonalityCatalog.mockResolvedValue(CATALOG);
  });

  it('renders every catalog preset, including ids the old hardcoded list never had', async () => {
    render(<PersonalityStylePicker value="professional" onChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /agent.personality.styles.professional/ })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /agent.personality.styles.concise/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /agent.personality.styles.zen-custom/ })).toBeInTheDocument();
  });

  it('reports the picked style id', async () => {
    const onChange = vi.fn();
    render(<PersonalityStylePicker value="professional" onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /agent.personality.styles.concise/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /agent.personality.styles.concise/ }));

    expect(onChange).toHaveBeenCalledWith('concise');
  });

  it('ignores clicks while readonly', async () => {
    const onChange = vi.fn();
    render(<PersonalityStylePicker value="professional" onChange={onChange} readonly />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /agent.personality.styles.concise/ })).toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /agent.personality.styles.concise/ }));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('previews the selected preset description and example', async () => {
    render(<PersonalityStylePicker value="concise" onChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Direct and to-the-point responses')).toBeInTheDocument();
    });
    expect(screen.getByText('Wrap it in useMemo.')).toBeInTheDocument();
    expect(screen.queryByText('Here is a structured approach...')).not.toBeInTheDocument();
  });

  it('previews the Chinese copy when the UI locale is Chinese', async () => {
    mockLocale = 'zh-CN';
    render(<PersonalityStylePicker value="concise" onChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('极致简洁，高信息密度')).toBeInTheDocument();
    });
    expect(screen.getByText('用 useMemo 包住这个属性即可。')).toBeInTheDocument();
  });

  it('offers a retry when the catalog request fails', async () => {
    mockGetPersonalityCatalog.mockRejectedValueOnce(new Error('boom'));

    render(<PersonalityStylePicker value="professional" onChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('agent.personality.loadFailed')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('agent.personality.retry'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /agent.personality.styles.concise/ })).toBeInTheDocument();
    });
    expect(mockGetPersonalityCatalog).toHaveBeenCalledTimes(2);
  });
});
