import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { FrameEmbed } from '../providers/types';

const stableT = (key: string, values?: Record<string, string>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { EmbedFacade } from '../EmbedFacade';
import { EmbedFail } from '../EmbedFail';

const descriptor: FrameEmbed = {
  id: 'yt-1',
  label: 'YouTube',
  provider: 'youtube',
  renderer: 'frame',
  sourceUrl: 'https://www.youtube.com/watch?v=abc',
  embedUrl: 'https://www.youtube.com/embed/abc',
  aspectRatio: 16 / 9,
};

describe('EmbedFacade', () => {
  it('labels the load button and the options menu through translations', () => {
    render(<EmbedFacade descriptor={descriptor} onLoad={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'load:YouTube' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'moreOptions' }));
    expect(screen.getByRole('button', { name: 'alwaysAllow:YouTube' })).toBeInTheDocument();
  });
});

describe('EmbedFail', () => {
  it('names the failed provider through a translation', () => {
    render(<EmbedFail label="YouTube" />);

    expect(screen.getByText('loadFailed:YouTube')).toBeInTheDocument();
  });
});
