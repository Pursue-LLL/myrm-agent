/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PresentationGeneratorModal } from '../PresentationGeneratorModal';
import * as presentationService from '@/services/presentation';
import type { PresentationArtifactResponse } from '@/services/presentation';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('PresentationGeneratorModal component', () => {
  const mockResponse: PresentationArtifactResponse = {
    id: 'deck-xyz',
    topic: 'Cloud Agent Architecture',
    template_style: 'enterprise_blue',
    total_slides: 4,
    slides: [
      {
        slide_number: 1,
        title: 'Cloud Agent Architecture',
        layout: 'title_hero',
        elements: [],
      },
    ],
    file_name: 'cloud_agent.pptx',
    file_size_bytes: 20480,
    download_url: '/api/v1/presentation/deck-xyz/download',
    created_at: '2026-10-12T10:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModalMock(this: HTMLDialogElement) {
        this.open = true;
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function closeMock(this: HTMLDialogElement) {
        this.open = false;
      };
    }
  });

  it('renders modal form inputs properly when open', () => {
    const handleClose = vi.fn();
    render(<PresentationGeneratorModal isOpen={true} onClose={handleClose} />);

    expect(screen.getByText('modalTitle')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('topicPlaceholder')).toBeInTheDocument();
    expect(screen.getByText('generateButton')).toBeInTheDocument();
  });

  it('triggers generatePresentation and switches to previewer on success', async () => {
    const generateSpy = vi
      .spyOn(presentationService, 'generatePresentation')
      .mockResolvedValueOnce(mockResponse);

    const handleClose = vi.fn();
    render(
      <PresentationGeneratorModal
        isOpen={true}
        onClose={handleClose}
        defaultTopic="Next Gen Multi-Agent"
      />,
    );

    const generateBtn = screen.getByText('generateButton');
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(generateSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: 'Next Gen Multi-Agent',
          template_style: 'enterprise_blue',
          slides_count: 5,
          enable_illustrations: true,
        }),
      );
    });

    // Check that previewer loaded
    await waitFor(() => {
      expect(screen.getByText('+ New Presentation')).toBeInTheDocument();
      expect(screen.getByText('cloud_agent.pptx')).toBeInTheDocument();
    });
  });

  it('displays error message when generation fails', async () => {
    vi.spyOn(presentationService, 'generatePresentation').mockRejectedValueOnce(
      new Error('Server GPU memory overload'),
    );

    const handleClose = vi.fn();
    render(
      <PresentationGeneratorModal
        isOpen={true}
        onClose={handleClose}
        defaultTopic="Fault Tolerance"
      />,
    );

    const generateBtn = screen.getByText('generateButton');
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText('Server GPU memory overload')).toBeInTheDocument();
    });
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<PresentationGeneratorModal isOpen={true} onClose={handleClose} />);

    const closeBtn = screen.getByLabelText('closeAriaLabel');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
