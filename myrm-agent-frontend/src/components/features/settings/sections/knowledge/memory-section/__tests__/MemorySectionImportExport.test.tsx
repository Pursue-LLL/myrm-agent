import { fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import {
  archive,
  attr,
  byTitle,
  click,
  downloads,
  pickImportFile,
  renderSection,
  resetKit,
  service,
  toast,
  toastArgs,
} from './memorySectionTestKit';
import { dryRunOf, fileOf } from './memorySectionFixtures';

const MAX_BYTES = 50 * 1024 * 1024;

const saveDialog = vi.hoisted(() => ({ cancelled: false }));

/** The real helper, except that a test can make the user cancel the desktop save dialog. */
vi.mock('@/lib/utils/fileUtils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/utils/fileUtils')>();
  return {
    ...actual,
    triggerDownload: (blob: Blob, filename: string) =>
      saveDialog.cancelled ? Promise.resolve(false) : actual.triggerDownload(blob, filename),
  };
});

const isSpinning = (title: string) => byTitle(title).querySelector('svg')?.classList.contains('animate-spin');

beforeEach(() => {
  resetKit();
  saveDialog.cancelled = false;
});

describe('MemorySection JSON export', () => {
  it('saves the memories as a dated, pretty-printed JSON file and confirms with the count', async () => {
    renderSection();
    await click(byTitle('export'));

    expect(downloads.names).toHaveLength(1);
    expect(downloads.names[0]).toMatch(/^memories-\d{4}-\d{2}-\d{2}\.json$/);
    const [blob] = downloads.blobs;
    expect(blob.type).toBe('application/json');
    expect(await blob.text()).toBe(JSON.stringify({ version: 1, data: { semantic: [{ id: 'm1' }] } }, null, 2));
    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'exportSuccess',
      description: 'exportSuccessDesc|{"count":2}',
    });
  });

  it('stays quiet when the user cancels the save dialog', async () => {
    saveDialog.cancelled = true;
    renderSection();

    await click(byTitle('export'));

    expect(downloads.names).toEqual([]);
    expect(toast).not.toHaveBeenCalled();
    expect(byTitle('export')).toBeEnabled();
  });

  it('refuses to save an empty export', async () => {
    service.exportMemories.mockResolvedValue({ version: 1, data: {}, total_count: 0 });
    renderSection();

    await click(byTitle('export'));

    expect(downloads.names).toEqual([]);
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'noMemoriesToExport', variant: 'destructive' });
  });

  it.each([
    ['an Error', new Error('server down'), 'server down'],
    ['something else', 'nope', 'unknownError'],
  ])('reports an export that failed with %s', async (_label, failure, expectedText) => {
    service.exportMemories.mockRejectedValue(failure);
    renderSection();

    await click(byTitle('export'));

    expect(downloads.names).toEqual([]);
    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'exportFailed',
      description: expectedText,
      variant: 'destructive',
    });
  });

  it('disables the button and spins while the export runs', async () => {
    const request = deferred<{ version: number; data: object; total_count: number }>();
    service.exportMemories.mockReturnValue(request.promise);
    renderSection();

    await click(byTitle('export'));
    expect(byTitle('export')).toBeDisabled();
    expect(isSpinning('export')).toBe(true);

    request.resolve({ version: 1, data: {}, total_count: 1 });
    await settle();
    expect(byTitle('export')).toBeEnabled();
    expect(isSpinning('export')).toBe(false);
  });
});

describe('MemorySection Markdown export', () => {
  it('runs the export and confirms it', async () => {
    renderSection();

    await click(byTitle('exportMarkdown'));

    expect(service.exportMemoriesMarkdown).toHaveBeenCalledOnce();
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'exportSuccess' });
  });

  it('reports a failed export', async () => {
    service.exportMemoriesMarkdown.mockRejectedValue(new Error('zip failed'));
    renderSection();

    await click(byTitle('exportMarkdown'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'exportFailed',
      description: 'zip failed',
      variant: 'destructive',
    });
  });

  it('disables the button while the export runs', async () => {
    const request = deferred<void>();
    service.exportMemoriesMarkdown.mockReturnValue(request.promise);
    renderSection();

    await click(byTitle('exportMarkdown'));
    expect(byTitle('exportMarkdown')).toBeDisabled();

    request.resolve();
    await settle();
    expect(byTitle('exportMarkdown')).toBeEnabled();
  });
});

describe('MemorySection import: choosing a file', () => {
  it('previews a JSON file and opens the review dialog', async () => {
    const { container } = renderSection();
    const clearInput = await pickImportFile(container, fileOf('memories.json', '{"version":1,"data":{}}'));

    expect(archive.dryRunImportMemories).toHaveBeenCalledExactlyOnceWith({ version: 1, data: {} }, 'auto');
    expect(attr('import-review', 'data-open')).toBe('true');
    expect(attr('import-review', 'data-expires')).toBe('2030-02-01T00:00:00Z');
    expect(attr('import-review', 'data-source')).toBe('native_json');
    expect(attr('import-review', 'data-importing')).toBe('false');
    expect(clearInput).toHaveBeenCalledExactlyOnceWith('');
  });

  it('keeps the valid lines of a JSONL transcript and tags the source', async () => {
    const lines = ['{"type":"user","n":1}', 'not json', '', '{"type":"assistant","n":2}'].join('\n');
    const { container } = renderSection();
    await pickImportFile(container, fileOf('session.jsonl', lines));

    expect(archive.dryRunImportMemories).toHaveBeenCalledExactlyOnceWith(
      {
        jsonl_lines: [
          { type: 'user', n: 1 },
          { type: 'assistant', n: 2 },
        ],
        _source_hint: 'claude_code_jsonl',
      },
      'claude_code_jsonl',
    );
  });

  it('rejects a JSONL file without any valid line', async () => {
    const { container } = renderSection();
    await pickImportFile(container, fileOf('session.jsonl', 'garbage\nmore garbage'));

    expect(archive.dryRunImportMemories).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'importFailed',
      description: 'importJsonlNoValidLines',
      variant: 'destructive',
    });
    expect(attr('import-review', 'data-open')).toBe('false');
  });

  it('reports a file that is not valid JSON with the parser message', async () => {
    const { container } = renderSection();
    await pickImportFile(container, fileOf('memories.json', '{ nope'));

    expect(archive.dryRunImportMemories).not.toHaveBeenCalled();
    const [shown] = toastArgs();
    expect(shown).toMatchObject({ title: 'importFailed', variant: 'destructive' });
    expect(shown.description).not.toBe('unknownError');
    expect(shown.description).toEqual(expect.any(String));
  });

  it('turns away files above the size limit before reading them', async () => {
    const { container } = renderSection();
    const clearInput = await pickImportFile(container, fileOf('huge.json', '{}', MAX_BYTES + 1));

    expect(archive.dryRunImportMemories).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'importFailed',
      description: 'importFileTooLarge|{"maxMb":50}',
      variant: 'destructive',
    });
    expect(clearInput).toHaveBeenCalledExactlyOnceWith('');
    expect(isSpinning('import')).toBe(false);
  });

  it('accepts a file exactly at the size limit', async () => {
    const { container } = renderSection();
    await pickImportFile(container, fileOf('edge.json', '{}', MAX_BYTES));

    expect(archive.dryRunImportMemories).toHaveBeenCalledOnce();
  });

  it('reports a preview the server rejects and frees the button again', async () => {
    archive.dryRunImportMemories.mockRejectedValue(new Error('unsupported export'));
    const { container } = renderSection();
    const clearInput = await pickImportFile(container, fileOf('memories.json', '{}'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'importFailed',
      description: 'unsupported export',
      variant: 'destructive',
    });
    expect(attr('import-review', 'data-open')).toBe('false');
    expect(byTitle('import')).toBeEnabled();
    expect(clearInput).toHaveBeenCalledExactlyOnceWith('');
  });

  it('disables the import button and spins while the preview is prepared', async () => {
    const preview = deferred<ReturnType<typeof dryRunOf>>();
    archive.dryRunImportMemories.mockReturnValue(preview.promise);
    const { container } = renderSection();
    await pickImportFile(container, fileOf('memories.json', '{}'));

    expect(byTitle('import')).toBeDisabled();
    expect(isSpinning('import')).toBe(true);

    preview.resolve(dryRunOf());
    await settle();
    expect(byTitle('import')).toBeEnabled();
  });

  it('ignores a change event without a file', async () => {
    const { container } = renderSection();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, { target: { files: [] } });
    await settle();

    expect(archive.dryRunImportMemories).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
  });

  it('opens the file picker from the import button', async () => {
    const { container } = renderSection();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    const open = vi.spyOn(input as HTMLInputElement, 'click').mockImplementation(() => undefined);

    await click(byTitle('import'));

    expect(open).toHaveBeenCalledOnce();
    expect(input).toHaveAttribute('accept', '.json,.jsonl');
  });
});
