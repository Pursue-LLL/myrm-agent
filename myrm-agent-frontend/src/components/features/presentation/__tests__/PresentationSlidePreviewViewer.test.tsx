/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PresentationSlidePreviewViewer } from '../PresentationSlidePreviewViewer';
import type { PresentationArtifactResponse } from '@/services/presentation';

const stableT = (key: string, options?: { current?: number; total?: number }) => {
    if (key === 'slideCounter' && options) {
      return `Slide ${options.current} of ${options.total}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PresentationSlidePreviewViewer component', () => {
  const mockArtifact: PresentationArtifactResponse = {
    id: 'test-pres-123',
    topic: 'Next-Gen Multi-Agent Collaboration',
    template_style: 'enterprise_blue',
    total_slides: 3,
    slides: [
      {
        slide_number: 1,
        title: 'Title Slide',
        subtitle: 'First slide subtitle',
        layout: 'title_hero',
        elements: [],
        speaker_notes: 'Welcome team to the architectural review.',
      },
      {
        slide_number: 2,
        title: 'Comparison Slide',
        subtitle: 'Old vs New',
        layout: 'two_column_comparison',
        elements: [
          {
            element_type: 'card',
            title: 'Legacy',
            body: 'Old architecture',
          },
          {
            element_type: 'card',
            title: 'Modern',
            body: 'New engine',
          },
        ],
        speaker_notes: 'Highlight cost savings here.',
      },
      {
        slide_number: 3,
        title: 'Summary Slide',
        subtitle: 'Final Takeaways',
        layout: 'summary_action',
        elements: [],
        speaker_notes: null,
      },
    ],
    file_name: 'test_deck.pptx',
    file_size_bytes: 40960,
    download_url: '/api/v1/presentation/test-pres-123/download',
    created_at: '2026-10-12T10:00:00Z',
  };

  it('renders header, topic, download button and thumbnails', () => {
    render(<PresentationSlidePreviewViewer artifact={mockArtifact} />);
    expect(screen.getByText('Next-Gen Multi-Agent Collaboration')).toBeInTheDocument();
    expect(screen.getByText(/40.0 KB/)).toBeInTheDocument();
    expect(screen.getByText('downloadPptx')).toBeInTheDocument();

    const downloadLink = screen.getByText('downloadPptx').closest('a');
    expect(downloadLink).toHaveAttribute('href', '/api/v1/presentation/test-pres-123/download');

    // 3 thumbnails in aside navigation
    const aside = screen.getByLabelText('Slide thumbnails');
    expect(aside).toBeInTheDocument();
  });

  it('navigates with previous and next buttons', () => {
    render(<PresentationSlidePreviewViewer artifact={mockArtifact} />);
    expect(screen.getByText('Slide 1 of 3')).toBeInTheDocument();

    const nextButtons = screen.getAllByText(/nextSlide/i);
    fireEvent.click(nextButtons[0]);
    expect(screen.getByText('Slide 2 of 3')).toBeInTheDocument();

    const prevButtons = screen.getAllByText(/previousSlide/i);
    fireEvent.click(prevButtons[0]);
    expect(screen.getByText('Slide 1 of 3')).toBeInTheDocument();
  });

  it('handles keyboard arrow navigation', () => {
    render(<PresentationSlidePreviewViewer artifact={mockArtifact} />);
    expect(screen.getByText('Slide 1 of 3')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(screen.getByText('Slide 2 of 3')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(screen.getByText('Slide 1 of 3')).toBeInTheDocument();
  });

  it('toggles speaker notes accordion', () => {
    render(<PresentationSlidePreviewViewer artifact={mockArtifact} />);
    const notesButton = screen.getByText('speakerNotes');
    expect(notesButton).toBeInTheDocument();

    // Notes initially closed
    expect(screen.queryByText('Welcome team to the architectural review.')).not.toBeInTheDocument();

    // Open notes
    fireEvent.click(notesButton);
    expect(screen.getByText('Welcome team to the architectural review.')).toBeInTheDocument();

    // Close notes
    fireEvent.click(notesButton);
    expect(screen.queryByText('Welcome team to the architectural review.')).not.toBeInTheDocument();
  });

  it('toggles slideshow fullscreen mode and exits via ESC', () => {
    render(<PresentationSlidePreviewViewer artifact={mockArtifact} />);
    const fullscreenButton = screen.getByText('fullscreenPresentation');
    fireEvent.click(fullscreenButton);

    expect(screen.getByText(/exitFullscreen/i)).toBeInTheDocument();

    // Exit via ESC key
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByText(/exitFullscreen/i)).not.toBeInTheDocument();
  });
});
