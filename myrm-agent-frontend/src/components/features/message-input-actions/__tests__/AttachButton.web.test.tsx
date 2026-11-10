import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import type { FileReference } from '@/services/file-service';
import useChatStore from '@/store/useChatStore';
import {
  chatFile,
  kit,
  makeFile,
  makeSizedFile,
  pickFiles as pick,
  renderAttach,
  resetAttachKit,
} from './attachButtonKit';

beforeEach(resetAttachKit);
afterEach(() => useChatStore.setState({ incognitoMode: false }));

const MB = 1024 * 1024;

const uploaded = (fileName: string): FileReference => ({
  id: `id:${fileName}`,
  fileName,
  fileExtension: fileName.split('.').pop() ?? '',
  fileType: 'uploaded',
  fileUrl: `/uploads/${fileName}`,
});

describe('AttachButton picking files in the browser', () => {
  it('opens the file picker when the button is clicked', () => {
    const view = renderAttach();
    const open = vi.spyOn(view.input(), 'click').mockImplementation(() => {});

    fireEvent.click(view.button());

    expect(open).toHaveBeenCalledTimes(1);
  });

  it('offers the supported file types and lets several be picked at once', () => {
    const { input } = renderAttach();

    expect(input().multiple).toBe(true);
    expect(input().accept.split(',')).toEqual(expect.arrayContaining(['.png', '.pdf', '.xlsx', '.mp4', '.mp3']));
    expect(input()).toHaveClass('hidden');
  });

  it('does nothing when the picker is dismissed without a choice', async () => {
    const view = renderAttach();

    await pick(view.input());

    expect(kit.admit).not.toHaveBeenCalled();
    expect(view.setFiles).not.toHaveBeenCalled();
  });

  it('clears the input so the same file can be picked again', async () => {
    const view = renderAttach();
    const setValue = vi.fn();
    Object.defineProperty(view.input(), 'value', { configurable: true, get: () => '', set: setValue });

    await pick(view.input(), makeFile('a.txt'));

    expect(setValue).toHaveBeenCalledWith('');
  });
});

describe('AttachButton uploading what was picked', () => {
  it('uploads the files and appends them, with their content hash, to the attachments', async () => {
    const view = renderAttach([chatFile('old.txt', { contentHash: 'hash:old.txt' })]);
    const [a, b] = [makeFile('a.pdf'), makeFile('b.png')];

    await pick(view.input(), a, b);

    expect(kit.resetUploadController).toHaveBeenCalledTimes(1);
    expect(kit.uploadFiles).toHaveBeenCalledExactlyOnceWith([a, b], expect.any(Function), kit.uploadSignal, {});
    expect(view.list.current.map((file) => [file.fileName, file.contentHash, file.fileUrl])).toEqual([
      ['old.txt', 'hash:old.txt', undefined],
      ['a.pdf', 'hash:a.pdf', '/uploads/a.pdf'],
      ['b.png', 'hash:b.png', '/uploads/b.png'],
    ]);
  });

  it('uploads what image admission hands back instead of what was picked', async () => {
    const view = renderAttach();
    const compressed = makeFile('photo.jpg');
    kit.admit.mockResolvedValue([compressed]);

    await pick(view.input(), makeFile('photo-original.png'));

    expect(kit.uploadFiles.mock.calls[0][0]).toEqual([compressed]);
    expect(view.list.current.map((file) => file.fileName)).toEqual(['photo.jpg']);
  });

  it('binds the upload to the conversation while it is incognito', async () => {
    useChatStore.setState({ incognitoMode: true, chatId: 'incognito-chat' });
    const view = renderAttach();

    await pick(view.input(), makeFile('a.txt'));

    expect(kit.uploadFiles.mock.calls[0][3]).toEqual({ incognitoChatId: 'incognito-chat' });
  });

  it('shows the progress in place of the button until the upload is over', async () => {
    const upload = deferred<FileReference[]>();
    kit.uploadFiles.mockReturnValueOnce(upload.promise);
    const view = renderAttach();

    await pick(view.input(), makeFile('a.pdf'));
    expect(screen.queryByRole('button', { name: 'attach' })).toBeNull();
    expect(screen.getByText('0%')).toBeInTheDocument();

    act(() => kit.uploadFiles.mock.calls[0][1]?.({ loaded: 4, total: 10, percent: 40 }));
    expect(screen.getByText('40%')).toBeInTheDocument();

    await act(async () => upload.resolve([uploaded('a.pdf')]));
    expect(view.button()).toBeInTheDocument();
    expect(screen.queryByText('40%')).toBeNull();
  });

  it('keeps attachments that were added elsewhere while the upload was running', async () => {
    const upload = deferred<FileReference[]>();
    kit.uploadFiles.mockReturnValueOnce(upload.promise);
    const view = renderAttach([chatFile('old.txt')]);

    await pick(view.input(), makeFile('big.mp4'));
    view.list.current = [...view.list.current, chatFile('pasted.png')];
    await act(async () => upload.resolve([uploaded('big.mp4')]));

    expect(view.list.current.map((file) => file.fileName)).toEqual(['old.txt', 'pasted.png', 'big.mp4']);
  });
});

describe('AttachButton size and count limits', () => {
  it.each([
    ['video', 'big.mp4', 100 * MB, 'videoTooLarge', 'videoTooLargeDesc|100.0MB'],
    ['audio', 'long.mp3', 25 * MB, 'audioTooLarge', 'audioTooLargeDesc|25.0MB'],
  ])('refuses a %s over its limit, naming its size, and uploads nothing', async (_kind, name, limit, title, text) => {
    const view = renderAttach();

    await pick(view.input(), makeFile('fine.txt'), makeSizedFile(name, limit + 1));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title, description: text, duration: 5000 });
    expect(kit.uploadFiles).not.toHaveBeenCalled();
    expect(view.setFiles).not.toHaveBeenCalled();
  });

  it.each([
    ['video', 'exact.mp4', 100 * MB],
    ['audio', 'exact.mp3', 25 * MB],
  ])('accepts a %s of exactly its limit', async (_kind, name, limit) => {
    const view = renderAttach();

    await pick(view.input(), makeSizedFile(name, limit));

    expect(kit.toast).not.toHaveBeenCalled();
    expect(view.list.current.map((file) => file.fileName)).toEqual([name]);
  });

  it('leaves the size of other kinds of file to the general upload rules', async () => {
    const view = renderAttach();

    await pick(view.input(), makeSizedFile('huge.pdf', 120 * MB));

    expect(kit.toast).not.toHaveBeenCalled();
    expect(view.list.current.map((file) => file.fileName)).toEqual(['huge.pdf']);
  });

  it('refuses a pick that would take the attachments past 20, naming how many there are', async () => {
    const attached = Array.from({ length: 19 }, (_, index) => chatFile(`f${index}.txt`));
    const view = renderAttach(attached);

    await pick(view.input(), makeFile('a.txt'), makeFile('b.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'uploadLimit', description: 'uploadLimitDesc|19' });
    expect(kit.uploadFiles).not.toHaveBeenCalled();
  });

  it('accepts a pick that takes the attachments to exactly 20', async () => {
    const attached = Array.from({ length: 19 }, (_, index) => chatFile(`f${index}.txt`));
    const view = renderAttach(attached);

    await pick(view.input(), makeFile('last.txt'));

    expect(view.list.current).toHaveLength(20);
  });
});

describe('AttachButton skipping files that are already attached', () => {
  it('skips a file whose content is attached already, says which, and uploads the rest', async () => {
    const view = renderAttach([chatFile('attached.txt', { contentHash: 'hash:copy.txt' })]);

    await pick(view.input(), makeFile('copy.txt'), makeFile('fresh.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'duplicateFiles', description: 'copy.txt' });
    expect(kit.uploadFiles.mock.calls[0][0].map((file) => file.name)).toEqual(['fresh.txt']);
    expect(view.list.current.map((file) => file.fileName)).toEqual(['attached.txt', 'fresh.txt']);
  });

  it('lists every file that was skipped', async () => {
    const view = renderAttach([
      chatFile('first.txt', { contentHash: 'hash:one.txt' }),
      chatFile('second.txt', { contentHash: 'hash:two.txt' }),
    ]);

    await pick(view.input(), makeFile('one.txt'), makeFile('two.txt'), makeFile('fresh.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'duplicateFiles', description: 'one.txt, two.txt' });
  });

  it('uploads nothing, and leaves the button usable, when every picked file is a duplicate', async () => {
    const view = renderAttach([chatFile('attached.txt', { contentHash: 'hash:copy.txt' })]);

    await pick(view.input(), makeFile('copy.txt'));

    expect(kit.uploadFiles).not.toHaveBeenCalled();
    expect(kit.resetUploadController).not.toHaveBeenCalled();
    expect(view.setFiles).not.toHaveBeenCalled();
    expect(view.button()).toBeInTheDocument();
  });

  it('treats two picked files with the same content as one', async () => {
    kit.hashOf.mockResolvedValue('same-content');
    const view = renderAttach();

    await pick(view.input(), makeFile('first.txt'), makeFile('second.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'duplicateFiles', description: 'second.txt' });
    expect(view.list.current.map((file) => file.fileName)).toEqual(['first.txt']);
  });

  it('is not fooled by attachments that have no hash', async () => {
    const view = renderAttach([chatFile('legacy.txt')]);

    await pick(view.input(), makeFile('new.txt'));

    expect(kit.toast).not.toHaveBeenCalled();
    expect(view.list.current.map((file) => file.fileName)).toEqual(['legacy.txt', 'new.txt']);
  });
});

describe('AttachButton when an upload goes wrong', () => {
  it('says so when the server returned no file at all', async () => {
    kit.uploadFiles.mockResolvedValue([]);
    const view = renderAttach();

    await pick(view.input(), makeFile('a.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'uploadFailed', description: 'unknownError' });
    expect(view.setFiles).not.toHaveBeenCalled();
    expect(view.button()).toBeInTheDocument();
  });

  it.each([
    ['an error with a message', new Error('disk full'), 'disk full'],
    ['something that is not an error', 'nope', 'uploadFailedRetry'],
  ])('shows the reason for %s and gives the button back', async (_what, failure, text) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    kit.uploadFiles.mockRejectedValue(failure);
    const view = renderAttach();

    await pick(view.input(), makeFile('a.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'uploadFailed', description: text });
    expect(view.setFiles).not.toHaveBeenCalled();
    expect(view.button()).toBeInTheDocument();
  });

  it('still reports a browser error that is not a cancellation', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    kit.uploadFiles.mockRejectedValue(new DOMException('offline', 'NetworkError'));
    const view = renderAttach();

    await pick(view.input(), makeFile('a.txt'));

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ title: 'uploadFailed' }));
  });

  it('stays quiet when the upload was cancelled', async () => {
    kit.uploadFiles.mockRejectedValue(new DOMException('cancelled', 'AbortError'));
    const view = renderAttach();

    await pick(view.input(), makeFile('a.txt'));

    expect(kit.toast).not.toHaveBeenCalled();
    expect(view.button()).toBeInTheDocument();
  });
});
