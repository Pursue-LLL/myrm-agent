/**
 * [INPUT]
 * - services/workflowTemplates::WorkflowTemplateDetailResponse (POS: workflow template REST DTO)
 *
 * [OUTPUT]
 * - buildWorkflowTemplateBundle, parseWorkflowTemplateBundle, downloadWorkflowTemplateBundle
 *
 * [POS]
 * Client-side v1 JSON bundle for workflow template backup and import. Mirrors server slug rules.
 */

import type { WorkflowTemplateDetailResponse } from '@/services/workflowTemplates';

export const WORKFLOW_TEMPLATE_BUNDLE_VERSION = '1' as const;
export const WORKFLOW_TEMPLATE_IMPORT_MAX_BYTES = 512 * 1024;

const TEMPLATE_ID_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;

export interface WorkflowTemplateBundle {
  version: typeof WORKFLOW_TEMPLATE_BUNDLE_VERSION;
  template: {
    templateId: string;
    displayName: string;
    scriptCode: string;
    trustLatch: boolean;
  };
}

export interface ParsedWorkflowTemplateImport {
  templateId: string;
  displayName: string;
  scriptCode: string;
  trustLatch: boolean;
}

export type ParseWorkflowTemplateBundleResult =
  { ok: true; value: ParsedWorkflowTemplateImport } | { ok: false; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readNonEmptyString(record: Record<string, unknown>, key: string): string | null {
  const raw = record[key];
  if (typeof raw !== 'string') {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function normalizeTemplateId(raw: string): string {
  let cleaned = raw.trim().toLowerCase().replace(/_/g, '-');
  cleaned = cleaned.replace(/[^a-z0-9-]+/g, '-');
  cleaned = cleaned.replace(/-{2,}/g, '-').replace(/^-+|-+$/g, '');
  return cleaned;
}

export function isValidTemplateId(templateId: string): boolean {
  return TEMPLATE_ID_PATTERN.test(templateId);
}

export function buildWorkflowTemplateBundle(detail: WorkflowTemplateDetailResponse): WorkflowTemplateBundle {
  return {
    version: WORKFLOW_TEMPLATE_BUNDLE_VERSION,
    template: {
      templateId: detail.template.template_id,
      displayName: detail.template.display_name,
      scriptCode: detail.script_code,
      trustLatch: detail.template.trust_latch,
    },
  };
}

export function serializeWorkflowTemplateBundle(bundle: WorkflowTemplateBundle): string {
  return JSON.stringify(bundle, null, 2);
}

export function parseWorkflowTemplateBundle(raw: string): ParseWorkflowTemplateBundleResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, error: 'invalid_json' };
  }

  if (!isRecord(parsed)) {
    return { ok: false, error: 'invalid_format' };
  }

  const version = parsed.version;
  if (version !== WORKFLOW_TEMPLATE_BUNDLE_VERSION) {
    return { ok: false, error: 'unsupported_version' };
  }

  const template = parsed.template;
  if (!isRecord(template)) {
    return { ok: false, error: 'invalid_format' };
  }

  const rawTemplateId = readNonEmptyString(template, 'templateId');
  const displayName = readNonEmptyString(template, 'displayName');
  const scriptCode = readNonEmptyString(template, 'scriptCode');
  if (!rawTemplateId || !displayName || !scriptCode) {
    return { ok: false, error: 'invalid_format' };
  }

  const templateId = normalizeTemplateId(rawTemplateId);
  if (!isValidTemplateId(templateId)) {
    return { ok: false, error: 'invalid_template_id' };
  }

  const trustLatch = template.trustLatch;
  if (typeof trustLatch !== 'boolean') {
    return { ok: false, error: 'invalid_format' };
  }

  return {
    ok: true,
    value: {
      templateId,
      displayName,
      scriptCode,
      trustLatch,
    },
  };
}

export function workflowTemplateExportFilename(templateId: string): string {
  const safeId = templateId
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  const base = safeId.length > 0 ? safeId : 'workflow-template';
  return `${base}.myrm-workflow.json`;
}

export function downloadWorkflowTemplateBundle(bundle: WorkflowTemplateBundle, filename: string): void {
  const blob = new Blob([serializeWorkflowTemplateBundle(bundle)], {
    type: 'application/json;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.click();
  URL.revokeObjectURL(url);
}
