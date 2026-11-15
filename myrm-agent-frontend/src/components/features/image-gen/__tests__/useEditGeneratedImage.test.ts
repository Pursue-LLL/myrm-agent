import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import { useEditGeneratedImage } from '../useEditGeneratedImage';

const focusMessageInput = vi.hoisted(() => vi.fn());

vi.mock('@/lib/chat/focusMessageInput', () => ({ focusMessageInput }));

function edit(image: Parameters<ReturnType<typeof useEditGeneratedImage>>[0]) {
  const { result } = renderHook(() => useEditGeneratedImage());
  act(() => result.current(image));
}

describe('useEditGeneratedImage', () => {
  beforeEach(() => {
    focusMessageInput.mockClear();
    useChatStore.setState({ files: [], inputMessage: '' });
  });

  it('puts the clicked image into the composer as an attachment that names the media', () => {
    edit({ url: 'media://media_abc', mimeType: 'image/png' });

    const [file] = useChatStore.getState().files;
    expect(useChatStore.getState().files).toHaveLength(1);
    expect(file).toMatchObject({
      mediaId: 'media_abc',
      fileName: 'media_abc.png',
      fileExtension: 'png',
      fileType: 'uploaded',
      status: 'ready',
    });
    expect(file.id).toBeUndefined();
    expect(file.localPath).toBeUndefined();
    expect(file.fileUrl).toMatch(/\/api\/v1\/media\/media_abc\/file$/);
  });

  it('prefills the edit instruction and moves the cursor to the message box', () => {
    edit({ url: 'media://media_abc' });

    expect(useChatStore.getState().inputMessage).toBe('editPromptPrefix');
    expect(focusMessageInput).toHaveBeenCalledTimes(1);
  });

  it('keeps what the user already typed instead of overwriting it with the prefix', () => {
    useChatStore.setState({ inputMessage: 'make the sky purple' });

    edit({ url: 'media://media_abc' });

    expect(useChatStore.getState().inputMessage).toBe('make the sky purple');
  });

  it('attaches an image once however often it is clicked, and adds other images next to it', () => {
    const { result } = renderHook(() => useEditGeneratedImage());

    act(() => result.current({ url: 'media://media_abc' }));
    act(() => result.current({ url: 'media://media_abc' }));
    act(() => result.current({ url: 'media://media_def' }));

    expect(useChatStore.getState().files.map((file) => file.mediaId)).toEqual(['media_abc', 'media_def']);
  });

  it('keeps the files that were already attached', () => {
    useChatStore.setState({
      files: [{ id: 'f1', fileName: 'notes.pdf', fileExtension: 'pdf', fileType: 'uploaded' }],
    });

    edit({ url: 'media://media_abc' });

    expect(useChatStore.getState().files.map((file) => file.fileName)).toEqual(['notes.pdf', 'media_abc.png']);
  });

  it.each([
    ['image/jpeg', 'jpg'],
    ['image/webp', 'webp'],
    ['image/png; charset=binary', 'png'],
    ['application/octet-stream', 'png'],
    [undefined, 'png'],
  ])('names the attachment after the media type %s', (mimeType, extension) => {
    edit({ url: 'media://media_abc', mimeType });

    expect(useChatStore.getState().files[0]).toMatchObject({
      fileName: `media_abc.${extension}`,
      fileExtension: extension,
    });
  });

  it.each(['https://cdn.example/fox.png', '/api/v1/media/media_abc/file', 'media://', ''])(
    'does nothing for %j, which names no media-library entry',
    (url) => {
      edit({ url });

      expect(useChatStore.getState().files).toEqual([]);
      expect(useChatStore.getState().inputMessage).toBe('');
      expect(focusMessageInput).not.toHaveBeenCalled();
    },
  );
});
