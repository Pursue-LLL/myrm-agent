import { render, screen } from '@testing-library/react';
import type { FUniver } from '@univerjs/core/facade';
import type { createUniver } from '@univerjs/presets';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { expectDefined, expectNonNull } from '@/test-utils/expectDefined';
import SpreadsheetEditor from '../index';

type CreateUniverOptions = Parameters<typeof createUniver>[0];

const { translate, univerApis } = vi.hoisted(() => ({
  translate: (key: string) => key,
  univerApis: [] as FUniver[],
}));

vi.mock('next-intl', () => ({ useTranslations: () => translate }));
vi.mock('@univerjs/preset-sheets-core', () => ({ UniverSheetsCorePreset: () => ({}) }));
vi.mock('@univerjs/preset-sheets-core/locales/en-US', () => ({ default: {} }));
// The real Univer core and sheets facade, without the render engine and UI that jsdom cannot host: the editor's
// command-event wiring runs against the API surface of the installed library, not against a hand-written fake.
vi.mock('@univerjs/presets', async () => {
  const { LocaleType, Univer } = await import('@univerjs/core');
  const { FUniver } = await import('@univerjs/core/facade');
  const { UniverSheetsPlugin } = await import('@univerjs/sheets');
  await import('@univerjs/sheets/facade');
  return {
    LocaleType,
    mergeLocales: (...locales: Record<string, unknown>[]) => Object.assign({}, ...locales),
    createUniver: ({ locale, locales }: CreateUniverOptions) => {
      const univer = new Univer({ locale, locales });
      univer.registerPlugin(UniverSheetsPlugin);
      const univerAPI = FUniver.newAPI(univer);
      univerApis.push(univerAPI);
      return { univer, univerAPI };
    },
  };
});

async function sampleWorkbookBytes(): Promise<ArrayBuffer> {
  const XLSX = await import('xlsx');
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([['item', 'qty']]), 'Sheet1');
  return new Uint8Array(XLSX.write(workbook, { bookType: 'xlsx', type: 'array' })).buffer;
}

async function renderOpenedEditor(onDirty: (dirty: boolean) => void): Promise<void> {
  const bytes = await sampleWorkbookBytes();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(bytes)),
  );
  render(<SpreadsheetEditor previewUrl="/files/sales.xlsx" filename="sales.xlsx" onSave={vi.fn()} onDirty={onDirty} />);
  await screen.findByText('spreadsheet.saveChanges');
}

async function editCell(address: string): Promise<void> {
  const api = univerApis.at(-1);
  expectDefined(api, 'univer api');
  const workbook = api.getActiveWorkbook();
  expectNonNull(workbook, 'active workbook');
  await workbook.getActiveSheet().getRange(address).setValue('edited');
}

describe('SpreadsheetEditor command events', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens the workbook instead of falling into the load-error state', async () => {
    await renderOpenedEditor(vi.fn());

    expect(screen.queryByText(/spreadsheet\.loadError/)).toBeNull();
  });

  it('stays clean until the first edit, then reports dirty exactly once', async () => {
    const onDirty = vi.fn();
    await renderOpenedEditor(onDirty);
    expect(onDirty).not.toHaveBeenCalled();

    await editCell('A1');
    expect(onDirty).toHaveBeenCalledExactlyOnceWith(true);

    await editCell('B2');
    expect(onDirty).toHaveBeenCalledTimes(1);
  });
});
