import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ToolImageOutput } from '@/store/chat/types';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/image-editor/ImageEditor', () => ({ default: () => null }));

import ToolImageGallery from '../ToolImageGallery';

const images: ToolImageOutput[] = [
  { url: 'https://example.com/one.png', mimeType: 'image/png', toolName: 'browser' },
  { url: 'https://example.com/two.png', mimeType: 'image/png', toolName: 'desktop' },
];

describe('ToolImageGallery', () => {
  it('names each thumbnail by tool and position through a translation', () => {
    render(<ToolImageGallery images={images} />);

    expect(screen.getByAltText('toolImage.thumbnailAlt:browser|1')).toBeInTheDocument();
    expect(screen.getByAltText('toolImage.thumbnailAlt:desktop|2')).toBeInTheDocument();
  });

  it('labels every lightbox control and the full-size image through translations', () => {
    render(<ToolImageGallery images={images} />);
    fireEvent.click(screen.getByAltText('toolImage.thumbnailAlt:browser|1'));

    expect(screen.getByRole('dialog', { name: 'toolImage.lightboxLabel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'attachment_download' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'toolImage.lightboxClose' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'toolImage.lightboxNext' })).toBeInTheDocument();
    expect(screen.getByAltText('toolImage.lightboxAlt:browser')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'toolImage.lightboxNext' }));
    expect(screen.getByRole('button', { name: 'toolImage.lightboxPrevious' })).toBeInTheDocument();
    expect(screen.getByAltText('toolImage.lightboxAlt:desktop')).toBeInTheDocument();
  });
});
