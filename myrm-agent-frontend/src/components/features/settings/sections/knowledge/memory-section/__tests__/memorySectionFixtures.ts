import type { Memory, MemoryPaginationInfo } from '@/services/memory';
import type { MemoryImportConfirmResponse, MemoryImportDryRunResponse } from '@/services/memory/archive';

/** Data builders for the memory panel tests: minimal valid fields, so a test overrides only what it cares about. */

export const memoryOf = (id: string, fields: Partial<Memory> = {}): Memory => ({
  id,
  memory_type: 'semantic',
  content: `content of ${id}`,
  status: 'active',
  created_at: '2030-01-01T00:00:00Z',
  updated_at: '2030-01-01T00:00:00Z',
  ...fields,
});

export const pageOf = (page: number, hasNext: boolean, total = 1): MemoryPaginationInfo => ({
  page,
  page_size: 20,
  total,
  total_pages: hasNext ? page + 1 : page,
  has_next: hasNext,
  has_prev: page > 1,
});

export const dryRunOf = (fields: Partial<MemoryImportDryRunResponse> = {}): MemoryImportDryRunResponse => ({
  dry_run_id: 'dry-1',
  payload_hash: 'hash',
  expires_at: '2030-02-01T00:00:00Z',
  result: {
    summary: {
      source: 'native_json',
      version: '1',
      total_items: 4,
      mapped_items: 4,
      unmapped_items: 0,
      status: 'ready',
    },
    mappings: [],
    warnings: [],
    normalized_data: {},
  },
  pending_skills: [],
  pending_skills_total: 0,
  coverage_items: [],
  migration_lanes: [],
  ...fields,
});

export const confirmOf = (fields: Partial<MemoryImportConfirmResponse> = {}): MemoryImportConfirmResponse => ({
  imported: {},
  total_imported: 3,
  import_batch_id: 'batch-1',
  payload_hash: 'hash',
  source: 'native_json',
  transaction_items: 3,
  ...fields,
});

/** A `File` for the import input; `size` can be forced to exercise the upload limit. */
export const fileOf = (name: string, content: string, size?: number): File => {
  const file = new File([content], name);
  if (size !== undefined) {
    Object.defineProperty(file, 'size', { value: size });
  }
  return file;
};
