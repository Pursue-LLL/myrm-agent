import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { File } from '@/store/chat/types';
import AttachList from '../AttachList';

vi.mock('@/components/features/image-editor/ImageEditor', () => ({
  default: ({ onComplete }: { onComplete: (blob: Blob) => void }) => (
    <button type="button" onClick={() => onComplete(new Blob(['annotated'], { type: 'image/png' }))}>
      apply-annotation
    </button>
  ),
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));

const generated: File = {
  fileName: 'media_abc.png',
  fileExtension: 'png',
  fileUrl: 'http://127.0.0.1:8080/api/v1/media/media_abc/file',
  fileType: 'uploaded',
  status: 'ready',
  mediaId: 'media_abc',
};

describe('AttachList annotation of an attached image', () => {
  it('detaches the annotated image from the media-library item it came from', async () => {
    const setFiles = vi.fn();
    render(<AttachList files={[generated]} setFiles={setFiles} clearCurrentSessionMessageId={vi.fn()} />);

    fireEvent.click(screen.getByTitle('Edit'));
    fireEvent.click(await screen.findByRole('button', { name: 'apply-annotation' }));

    await waitFor(() => expect(setFiles).toHaveBeenCalledTimes(1));
    const [updated] = setFiles.mock.calls[0][0] as File[];
    expect(updated.mediaId).toBeUndefined();
    expect(updated.fileUrl).toMatch(/^data:image\/png;base64,/);
    expect(updated.fileName).toBe('media_abc.png');
  });
});
