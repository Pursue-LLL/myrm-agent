/**
 * Stand-ins for what a polymorphic-card suite does not exercise: the translator, Monaco and the
 * heavier approval children. A `vi.mock` factory loads them lazily with `import()`.
 */
import type { ReactElement } from 'react';
import type { AllowAlwaysDuration, AllowAlwaysScope } from '@/lib/approval/allowAlwaysScope';

type TranslationValues = Record<string, string | number>;

export interface Translator {
  (key: string, values?: TranslationValues): string;
  has: (key: string) => boolean;
}

/** The translation keys that exist; `has()` is false for every other one. */
export const knownTranslationKeys = new Set<string>(['escalationReasons.network']);

const translators = new Map<string, Translator>();

/** `ns.key` or `ns.key:{values}`, one stable translator per namespace like next-intl's memoised hook. */
export const translatorFor = (namespace: string): Translator => {
  const existing = translators.get(namespace);
  if (existing) {
    return existing;
  }
  const translator: Translator = Object.assign(
    (key: string, values?: TranslationValues) =>
      values === undefined ? `${namespace}.${key}` : `${namespace}.${key}:${JSON.stringify(values)}`,
    { has: (key: string) => knownTranslationKeys.has(key) },
  );
  translators.set(namespace, translator);
  return translator;
};

export const nextIntlModule = { useTranslations: translatorFor, useLocale: () => 'en' };

interface EditorStubProps {
  value?: string;
  original?: string;
  modified?: string;
  language?: string;
  height?: string;
  onChange?: (value: string | undefined) => void;
}

/** A textarea for the editor and a data-carrying div for the diff editor; `clear` reports an empty editor as `undefined`. */
export const monacoModule = {
  LazyMonacoEditor: ({ value, language, height, onChange }: EditorStubProps) => (
    <div>
      <textarea
        data-testid="editor"
        data-language={language}
        data-height={height}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
      />
      <button
        type="button"
        aria-label="clear editor"
        data-testid="editor-clear"
        onClick={() => onChange?.(undefined)}
      />
    </div>
  ),
  LazyMonacoDiffEditor: ({ original, modified, language }: EditorStubProps) => (
    <div data-testid="diff-editor" data-language={language} data-original={original} data-modified={modified} />
  ),
};

/** Marks which stand-in rendered, with the props it got (functions dropped by the JSON encoding). */
const propsStub = (name: string) =>
  function PropsStub(props: object): ReactElement {
    return <div data-testid={name} data-props={JSON.stringify(props)} />;
  };

/** The decoded props of a stand-in made by `propsStub`. */
export const propsOf = (element: HTMLElement): Record<string, unknown> =>
  JSON.parse(element.getAttribute('data-props') ?? '{}') as Record<string, unknown>;

export const subagentContentModule = { SubagentApprovalContent: propsStub('SubagentApprovalContent') };
export const skillContentModule = { SkillApprovalContent: propsStub('SkillApprovalContent') };
export const knowledgePatchModule = { KnowledgePatchContent: propsStub('KnowledgePatchContent') };
export const batchCostModule = { BatchCostApprovalContent: propsStub('BatchCostApprovalContent') };
export const highRiskModule = { HighRiskDomActionContent: propsStub('HighRiskDomActionContent') };
export const mcpElicitationModule = { McpElicitationContent: propsStub('McpElicitationContent') };
export const outboundDraftModule = { OutboundDraftApprovalBody: propsStub('OutboundDraftApprovalBody') };

/** Reports the editor text it was given and lets a test change it. */
export const toolClarificationModule = {
  ToolClarificationContent: ({
    editedArgs,
    onEditedArgsChange,
  }: {
    editedArgs: string;
    onEditedArgsChange: (value: string) => void;
  }) => (
    <div data-testid="ToolClarificationContent" data-edited-args={editedArgs}>
      <button type="button" onClick={() => onEditedArgsChange('{"fixed":true}')}>
        edit clarification
      </button>
    </div>
  ),
};

export const shellToolCallModule = { ShellToolCallApproval: propsStub('ShellToolCallApproval') };
export const compactRowModule = { default: propsStub('CompactFileWriteApprovalRow') };
export const saveSkillPreviewModule = { default: propsStub('SaveSkillApprovalPreview') };
export const scopeNoteLineModule = { default: propsStub('ApprovalScopeNoteLine') };
export const shellCommandDisplayModule = { default: propsStub('ShellCommandDisplay') };
export const evidenceScreenshotModule = { default: propsStub('HighRiskEvidenceScreenshot') };

interface EditViewStubProps {
  permissionTypeLabel: string;
  toolName: string;
  hideAllowAlways?: boolean;
  requestId: string;
  isLoading: boolean;
  shellCommand?: string;
  editedArgs: Record<string, string>;
  setEditedArgs: (args: Record<string, string>) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Reports what the card hands the edit view; its buttons type an edit, confirm or cancel. */
export const editModeViewModule = {
  default: (props: EditViewStubProps) => (
    <div
      data-testid="EditModeView"
      data-permission-type={props.permissionTypeLabel}
      data-tool-name={props.toolName}
      data-hide-allow-always={String(Boolean(props.hideAllowAlways))}
      data-request-id={props.requestId}
      data-loading={String(props.isLoading)}
      data-shell-command={props.shellCommand}
    >
      <button type="button" onClick={() => props.setEditedArgs({ ...props.editedArgs, command: 'echo edited' })}>
        type edit
      </button>
      <button type="button" onClick={props.onConfirm}>
        confirm edit
      </button>
      <button type="button" onClick={props.onCancel}>
        cancel edit
      </button>
    </div>
  ),
};

interface AllowAlwaysDialogStubProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  allowAlwaysScope: AllowAlwaysScope;
  setAllowAlwaysScope: (scope: AllowAlwaysScope) => void;
  allowAlwaysDuration?: AllowAlwaysDuration;
  setAllowAlwaysDuration?: (duration: AllowAlwaysDuration) => void;
  permissionTypeLabel: string;
  toolName: string;
  shellCommand?: string;
  onConfirm: () => void;
  isLoading: boolean;
}

/** Reports what the card hands the always-allow dialog; its buttons pick a scope and duration, confirm or close. */
export const allowAlwaysDialogModule = {
  default: (props: AllowAlwaysDialogStubProps) => (
    <div
      data-testid="AllowAlwaysConfirmDialog"
      data-open={String(props.open)}
      data-scope={props.allowAlwaysScope}
      data-duration={props.allowAlwaysDuration}
      data-permission-type={props.permissionTypeLabel}
      data-tool-name={props.toolName}
      data-shell-command={props.shellCommand}
      data-loading={String(props.isLoading)}
    >
      <button type="button" onClick={() => props.setAllowAlwaysScope('pattern')}>
        pick pattern
      </button>
      <button type="button" onClick={() => props.setAllowAlwaysDuration?.('1h')}>
        pick hour
      </button>
      <button type="button" onClick={props.onConfirm}>
        confirm allow always
      </button>
      <button type="button" onClick={() => props.onOpenChange(false)}>
        close dialog
      </button>
    </div>
  ),
};
