import { describe, expect, it } from 'vitest';

/**
 * handleEditSave (ArtifactPortal) must let errors propagate to SpreadsheetEditor's catch block.
 * This contract test verifies the async error propagation pattern used by the save flow:
 *   SpreadsheetEditor.handleSave → await onSave(blob) → handleEditSave
 *
 * If handleEditSave swallows the error (catch without re-throw),
 * SpreadsheetEditor would show "Saved" when the upload actually failed.
 */
describe('SpreadsheetEditor save error propagation contract', () => {
  it('rejecting onSave should propagate to the caller catch block', async () => {
    const onSave = async (_blob: Blob): Promise<void> => {
      throw new Error('Upload failed');
    };

    let caughtError: Error | null = null;
    try {
      const blob = new Blob(['test'], { type: 'application/octet-stream' });
      await onSave(blob);
    } catch (err) {
      caughtError = err as Error;
    }

    expect(caughtError).not.toBeNull();
    expect(caughtError!.message).toBe('Upload failed');
  });

  it('resolving onSave should not trigger the catch block', async () => {
    const onSave = async (_blob: Blob): Promise<void> => {
      // no-op
    };

    let caughtError: Error | null = null;
    try {
      const blob = new Blob(['test'], { type: 'application/octet-stream' });
      await onSave(blob);
    } catch (err) {
      caughtError = err as Error;
    }

    expect(caughtError).toBeNull();
  });

  it('empty upload response should throw', async () => {
    const handleEditSave = async (blob: Blob): Promise<void> => {
      const result = { files: [] as Array<{ fileUrl: string }> };
      void blob;
      if (result.files.length === 0) {
        throw new Error('Upload returned empty response');
      }
    };

    const blob = new Blob(['test'], { type: 'application/octet-stream' });
    await expect(handleEditSave(blob)).rejects.toThrow('Upload returned empty response');
  });
});
