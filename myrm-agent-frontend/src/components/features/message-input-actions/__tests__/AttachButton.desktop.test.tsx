import { act, fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import type { FileReference } from '@/services/file-service';
import { chatFile, configureModels, kit, renderAttach, resetAttachKit, settle } from './attachButtonKit';

beforeEach(() => {
  resetAttachKit();
  kit.isTauri.mockReturnValue(true);
  kit.selectFiles.mockResolvedValue([]);
});

const local = (fileName: string): FileReference => ({
  fileName,
  fileExtension: fileName.split('.').pop() ?? '',
  fileType: 'local_path',
  localPath: `/home/me/${fileName}`,
});

async function clickAttach(view: ReturnType<typeof renderAttach>): Promise<void> {
  fireEvent.click(view.button());
  await settle();
}

describe('AttachButton choosing files on the desktop', () => {
  it('has no web file input and asks the system dialog instead', async () => {
    const view = renderAttach();
    expect(view.input()).toBeNull();

    await clickAttach(view);

    expect(kit.selectFiles).toHaveBeenCalledTimes(1);
  });

  it('appends the chosen files, as paths on disk, to the attachments', async () => {
    kit.selectFiles.mockResolvedValue([local('a.pdf'), local('b.csv')]);
    const view = renderAttach([chatFile('old.txt')]);

    await clickAttach(view);

    expect(view.list.current).toEqual([
      chatFile('old.txt'),
      { id: undefined, fileName: 'a.pdf', fileExtension: 'pdf', fileType: 'local_path', localPath: '/home/me/a.pdf' },
      { id: undefined, fileName: 'b.csv', fileExtension: 'csv', fileType: 'local_path', localPath: '/home/me/b.csv' },
    ]);
    expect(kit.uploadFiles).not.toHaveBeenCalled();
  });

  it('uploads the chosen images too, so the model gets a path it can edit, and keeps their paths on disk', async () => {
    kit.selectFiles.mockResolvedValue([local('a.png'), local('b.pdf')]);
    const view = renderAttach();

    await clickAttach(view);

    expect(kit.uploadPickedImages).toHaveBeenCalledTimes(1);
    expect(kit.uploadPickedImages.mock.calls[0][0]).toEqual([local('a.png'), local('b.pdf')]);
    expect(kit.uploadPickedImages.mock.calls[0][2]).toBe(kit.uploadSignal);
    expect(kit.resetUploadController).toHaveBeenCalledTimes(1);
    expect(view.list.current).toEqual([
      {
        id: 'id:a.png',
        fileName: 'a.png',
        fileExtension: 'png',
        fileType: 'local_path',
        localPath: '/home/me/a.png',
        fileUrl: '/uploads/a.png',
      },
      { id: undefined, fileName: 'b.pdf', fileExtension: 'pdf', fileType: 'local_path', localPath: '/home/me/b.pdf' },
    ]);
  });

  it.each([
    ['an error with a message', new Error('disk full'), 'disk full'],
    ['something that is not an error', 'nope', 'uploadFailedRetry'],
  ])('still attaches the images by path, and says the upload failed, for %s', async (_what, failure, text) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    kit.uploadPickedImages.mockRejectedValue(failure);
    kit.selectFiles.mockResolvedValue([local('a.png')]);
    const view = renderAttach();

    await clickAttach(view);

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'uploadFailed', description: text });
    expect(view.list.current).toEqual([
      { id: undefined, fileName: 'a.png', fileExtension: 'png', fileType: 'local_path', localPath: '/home/me/a.png' },
    ]);
    expect(view.button()).toBeInTheDocument();
  });

  it('adds nothing, and says nothing, when the dialog is dismissed', async () => {
    const view = renderAttach();

    await clickAttach(view);

    expect(view.setFiles).not.toHaveBeenCalled();
    expect(kit.toast).not.toHaveBeenCalled();
    expect(view.button()).toBeInTheDocument();
  });

  it('shows the busy indicator in place of the button while the dialog is open', async () => {
    const dialog = deferred<FileReference[]>();
    kit.selectFiles.mockReturnValueOnce(dialog.promise);
    const view = renderAttach();

    await clickAttach(view);
    expect(screen.queryByRole('button', { name: 'attach' })).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();

    await act(async () => dialog.resolve([]));
    expect(view.button()).toBeInTheDocument();
  });

  it('keeps attachments that were added elsewhere while the dialog was open', async () => {
    const dialog = deferred<FileReference[]>();
    kit.selectFiles.mockReturnValueOnce(dialog.promise);
    const view = renderAttach([chatFile('old.txt')]);

    await clickAttach(view);
    view.list.current = [...view.list.current, chatFile('pasted.png')];
    await act(async () => dialog.resolve([local('a.pdf')]));

    expect(view.list.current.map((file) => file.fileName)).toEqual(['old.txt', 'pasted.png', 'a.pdf']);
  });
});

describe('AttachButton refusing a desktop choice', () => {
  it('refuses files whose names are attached already, listing them', async () => {
    kit.selectFiles.mockResolvedValue([local('same.txt'), local('fresh.txt'), local('also-same.txt')]);
    const view = renderAttach([chatFile('same.txt'), chatFile('also-same.txt')]);

    await clickAttach(view);

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'duplicateFiles',
      description: 'duplicateFilesDesc|same.txt, also-same.txt',
    });
    expect(view.setFiles).not.toHaveBeenCalled();
  });

  it('refuses a choice that would take the attachments past 20, naming how many there are', async () => {
    kit.selectFiles.mockResolvedValue([local('a.txt'), local('b.txt')]);
    const view = renderAttach(Array.from({ length: 19 }, (_, index) => chatFile(`f${index}.txt`)));

    await clickAttach(view);

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'uploadLimit', description: 'uploadLimitDesc|19' });
    expect(view.setFiles).not.toHaveBeenCalled();
  });

  it('accepts a choice that takes the attachments to exactly 20', async () => {
    kit.selectFiles.mockResolvedValue([local('last.txt')]);
    const view = renderAttach(Array.from({ length: 19 }, (_, index) => chatFile(`f${index}.txt`)));

    await clickAttach(view);

    expect(view.list.current).toHaveLength(20);
  });
});

describe('AttachButton on the desktop when the models cannot see', () => {
  it('warns about images and still attaches them', async () => {
    configureModels({});
    kit.selectFiles.mockResolvedValue([local('a.png')]);
    const view = renderAttach();

    await clickAttach(view);

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('image');
    expect(view.list.current.map((file) => file.fileName)).toEqual(['a.png']);
  });

  it('does not warn about documents', async () => {
    configureModels({});
    kit.selectFiles.mockResolvedValue([local('a.pdf')]);
    const view = renderAttach();

    await clickAttach(view);

    expect(kit.visionToast).not.toHaveBeenCalled();
    expect(view.list.current).toHaveLength(1);
  });

  it('warns about video and still attaches it', async () => {
    configureModels({});
    kit.selectFiles.mockResolvedValue([local('clip.mp4')]);
    const view = renderAttach();

    await clickAttach(view);

    expect(kit.visionToast).toHaveBeenCalledExactlyOnceWith('video');
    expect(view.list.current).toHaveLength(1);
  });
});

describe('AttachButton when the system dialog fails', () => {
  it.each([
    ['an error with a message', new Error('permission denied'), 'permission denied'],
    ['something that is not an error', 'nope', 'retryHint'],
  ])('shows the reason for %s and gives the button back', async (_what, failure, text) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    kit.selectFiles.mockRejectedValue(failure);
    const view = renderAttach();

    await clickAttach(view);

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'fileSelectionFailed', description: text });
    expect(view.setFiles).not.toHaveBeenCalled();
    expect(view.button()).toBeInTheDocument();
  });
});
