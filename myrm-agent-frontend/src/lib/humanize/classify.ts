import type { ApprovalSurface } from './types';

const LOCAL_COMPACT_TOOLS = new Set([
  'file_write_tool',
  'file_edit_tool',
  'file_read_tool',
  'file_editor_tool',
  'file_editor_view_tool',
  'file_editor_create_tool',
  'file_editor_edit_tool',
  'text_editor_tool',
  'file_write',
  'file_edit',
  'write_file',
  'read_file',
  'replace_in_file',
]);

/** Low-risk local file ops render as compact approval rows. */
export function classifyApprovalSurface(toolName: string): ApprovalSurface {
  if (LOCAL_COMPACT_TOOLS.has(toolName)) {
    return 'compact';
  }
  if (toolName.startsWith('file_') && !toolName.includes('bash')) {
    return 'compact';
  }
  return 'full';
}
