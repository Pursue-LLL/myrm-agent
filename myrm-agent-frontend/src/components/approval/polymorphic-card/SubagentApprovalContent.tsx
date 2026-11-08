'use client';

import { useTranslations } from 'next-intl';
import ApprovalScopeNoteLine from '@/components/approval/ApprovalScopeNoteLine';
import CompactFileWriteApprovalRow from '@/components/approval/CompactFileWriteApprovalRow';
import SaveSkillApprovalPreview from '@/components/approval/SaveSkillApprovalPreview';
import { isSaveSkillApproval } from '@/lib/approval/saveSkillApproval';
import { isShellApprovalTool } from '@/lib/approval/shellCommandDisplay';
import { classifyApprovalSurface, humanizeApprovalTitle, resolveScopeNote } from '@/lib/humanize';
import type { ApprovalPayload } from '@/store/useApprovalStore';
import { getLanguageFromPath } from './languageFromPath';
import { ShellToolCallApproval } from './ShellToolCallApproval';

/** The tool calls a subagent wants to run, each in the surface that fits it: file write, shell, skill save or raw arguments. */
export function SubagentApprovalContent({ approval }: { approval: ApprovalPayload }) {
  const t = useTranslations('toolApproval');
  const tHumanize = useTranslations('humanize');
  const toolCalls = approval.payload?.tool_calls ?? [];
  const humanizeCallTitle = (toolName: string, args: unknown) =>
    humanizeApprovalTitle(
      toolName,
      typeof args === 'object' && args !== null ? (args as Record<string, unknown>) : {},
      tHumanize,
    );
  const payloadRecord = approval.payload ?? {};
  const workspaceRoot =
    typeof payloadRecord.workspaceRoot === 'string'
      ? payloadRecord.workspaceRoot
      : typeof (payloadRecord.extensions as { workspaceRoot?: string } | undefined)?.workspaceRoot === 'string'
        ? (payloadRecord.extensions as { workspaceRoot: string }).workspaceRoot
        : undefined;
  return (
    <div className="space-y-4">
      <h4 className="font-medium text-sm text-muted-foreground">{t('subagentApprovalRequired')}</h4>
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {toolCalls.map((call, idx: number) => {
          if (typeof call.args === 'object' && call.args !== null && classifyApprovalSurface(call.name) === 'compact') {
            const args = call.args as Record<string, unknown>;
            const filePath =
              (typeof args.path === 'string' && args.path) ||
              (typeof args.file_path === 'string' && args.file_path) ||
              '';
            const content = String(args.content ?? args.file_content ?? args.text ?? '');
            const language = getLanguageFromPath(filePath);
            const hasWriteContent = content.trim().length > 0;

            if (filePath || hasWriteContent) {
              const scope = resolveScopeNote(call.name, args, tHumanize);
              return (
                <CompactFileWriteApprovalRow
                  key={idx}
                  title={humanizeCallTitle(call.name, call.args)}
                  filePath={filePath}
                  content={content}
                  language={language}
                  viewChangesLabel={t('viewChanges')}
                  hideChangesLabel={t('hideChanges')}
                  scopeNote={scope.text}
                  scopeExternal={scope.external}
                />
              );
            }
          }

          // Shell / code execution tools
          if (isShellApprovalTool(call.name) && typeof call.args === 'object' && call.args !== null) {
            return <ShellToolCallApproval key={idx} call={call} workspaceRoot={workspaceRoot} />;
          }

          // save_skill / skill_manage save — bundle preview
          if (
            typeof call.args === 'object' &&
            call.args !== null &&
            isSaveSkillApproval(call.name, call.args as Record<string, unknown>)
          ) {
            const args = call.args as Record<string, unknown>;
            return (
              <div key={idx} className="rounded-lg border p-4 bg-muted/20 space-y-2">
                <div className="font-medium text-sm text-primary">{humanizeCallTitle(call.name, call.args)}</div>
                <ApprovalScopeNoteLine toolName={call.name} toolInput={args} tHumanize={tHumanize} />
                <SaveSkillApprovalPreview
                  toolInput={args}
                  showFullInstructionsLabel={t('saveSkill.showFullInstructions')}
                  showLessLabel={t('saveSkill.showLess')}
                  showAllLinesLabel={t('saveSkill.showAllLines')}
                  footerText={t('saveSkill.footer')}
                />
              </div>
            );
          }

          // Fallback for other tools
          return (
            <div key={idx} className="rounded-lg border p-4 bg-muted/50 space-y-2">
              <div className="font-medium text-sm text-primary">{humanizeCallTitle(call.name, call.args)}</div>
              {typeof call.args === 'object' && call.args !== null ? (
                <ApprovalScopeNoteLine
                  toolName={call.name}
                  toolInput={call.args as Record<string, unknown>}
                  tHumanize={tHumanize}
                />
              ) : null}
              <pre className="text-xs overflow-x-auto text-muted-foreground whitespace-pre-wrap break-all">
                {JSON.stringify(call.args, null, 2)}
              </pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}
