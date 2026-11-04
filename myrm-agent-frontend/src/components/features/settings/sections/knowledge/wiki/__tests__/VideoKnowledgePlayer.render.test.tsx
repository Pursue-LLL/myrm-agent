/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockLocale } from '@/test-utils/realIntl';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import { VideoKnowledgePlayer } from '../VideoKnowledgePlayer';

const chapters = [{ startSeconds: 0, endSeconds: 59, label: 'Intro' }];

describe('VideoKnowledgePlayer chapter navigation', () => {
  beforeEach(() => {
    intl.locale = 'en';
  });

  it('titles the chapter list in English', () => {
    render(<VideoKnowledgePlayer sourceUrl="https://example.com/clip.mp4" chapters={chapters} />);

    expect(screen.getByText('Jump to timestamp')).toBeInTheDocument();
  });

  it('titles the chapter list in Chinese', () => {
    intl.locale = 'zh';
    render(<VideoKnowledgePlayer sourceUrl="https://example.com/clip.mp4" chapters={chapters} />);

    expect(screen.getByText('时间戳快速导航')).toBeInTheDocument();
  });

  it('hides the list when the note has no chapters', () => {
    render(<VideoKnowledgePlayer sourceUrl="https://example.com/clip.mp4" />);

    expect(screen.queryByText('Jump to timestamp')).not.toBeInTheDocument();
  });
});
