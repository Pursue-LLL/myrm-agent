'use client';

/**
 * [INPUT]
 * - @/store/chat/types::ToolApprovalRequest (POS: 要展示的审批请求)
 * - @/lib/humanize (POS: 审批标题与 scope 说明)
 * - @/lib/approval/visualApprovalContext (POS: 桌面/浏览器视觉审批上下文)
 *
 * [OUTPUT]
 * - ApprovalDetails: 审批卡的内容区——标题与范围说明、风控/智能审核提示、意图与理由、命令/技能/diff/参数预览、涉及的域名；浏览器登录态审批改为 BrowserSessionView
 *
 * [POS]
 * 审批卡的只读展示部分；不持有任何决定状态，决定与按钮在 SingleApprovalCard 与 ApprovalActions。
 */

import { Globe, ShieldAlert, Terminal } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useMemo } from 'react';

import ApprovalScopeNoteLine from '@/components/approval/ApprovalScopeNoteLine';
import PtcHintBadges from '@/components/approval/PtcHintBadges';
import SaveSkillApprovalPreview from '@/components/approval/SaveSkillApprovalPreview';
import { Badge } from '@/components/primitives/badge';
import type { BrowserSessionApproval } from '@/lib/approval/browserSession';
import type { InputEntry } from '@/lib/approval/editedArgs';
import { resolveVisualApprovalContextForRequest } from '@/lib/approval/visualApprovalContext';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import { humanizeApprovalTitle } from '@/lib/humanize';
import useBrowserInspectorStore, { selectScopedBrowserViewData } from '@/store/useBrowserInspectorStore';
import useDesktopInspectorStore, { selectScopedDesktopViewData } from '@/store/useDesktopInspectorStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

import BrowserSessionView from './BrowserSessionView';
import ShellCommandDisplay from './ShellCommandDisplay';
import VisualApprovalHighlight from './VisualApprovalHighlight';

interface ApprovalDetailsProps {
  request: ToolApprovalRequest;
  browserSession: BrowserSessionApproval | null;
  shellCommand: string;
  inputEntries: InputEntry[];
  isSaveSkill: boolean;
  isHighRiskIntercepted: boolean;
  hideVisualHighlight: boolean;
  hideCompactPayload: boolean;
}

function diffFilePath(toolInput: Record<string, unknown>): string | undefined {
  for (const key of ['path', 'filePath', 'file_path']) {
    const value = toolInput[key];
    if (typeof value === 'string') {
      return value;
    }
  }
  return undefined;
}

export default function ApprovalDetails({
  request,
  browserSession,
  shellCommand,
  inputEntries,
  isSaveSkill,
  isHighRiskIntercepted,
  hideVisualHighlight,
  hideCompactPayload,
}: ApprovalDetailsProps) {
  const t = useTranslations('toolApproval');
  const tHumanize = useTranslations('humanize');

  const desktopViewData = useDesktopInspectorStore((s) => selectScopedDesktopViewData(s.viewData, request.chatId));
  const browserViewData = useBrowserInspectorStore((s) => selectScopedBrowserViewData(s.viewData, request.chatId));
  const visualContext = useMemo(
    () => resolveVisualApprovalContextForRequest(request, desktopViewData, browserViewData),
    [browserViewData, desktopViewData, request],
  );

  const approvalTitle = useMemo(
    () => humanizeApprovalTitle(request.toolName, request.toolInput, tHumanize),
    [request.toolInput, request.toolName, tHumanize],
  );

  if (browserSession) {
    return <BrowserSessionView action={browserSession.action} domain={browserSession.domain} />;
  }

  return (
    <>
      <div className="flex items-center flex-wrap gap-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-muted-foreground shrink-0" />
            <span className="text-sm font-medium truncate">{approvalTitle}</span>
          </div>
          <span className="text-xs pl-6 break-words block">
            <ApprovalScopeNoteLine toolName={request.toolName} toolInput={request.toolInput} tHumanize={tHumanize} />
          </span>
        </div>
        {request.ptcAnnotations ? <PtcHintBadges annotations={request.ptcAnnotations} t={t} /> : null}
      </div>

      {visualContext && !hideVisualHighlight && (
        <VisualApprovalHighlight visualContext={visualContext} className="mb-2" />
      )}

      {request.smartDenied && (
        <div className="flex items-center gap-2 rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2.5 mb-2">
          <ShieldAlert className="h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-amber-700 dark:text-amber-300">{t('smartDenied.title')}</p>
            {request.reviewerReason && (
              <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5 break-words">
                {request.reviewerReason}
              </p>
            )}
          </div>
        </div>
      )}

      {isHighRiskIntercepted && (
        <div
          data-testid="high-risk-intercepted-banner"
          className="flex items-center gap-2 rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-2.5 mb-2"
        >
          <ShieldAlert className="h-4 w-4 flex-shrink-0 text-rose-600 dark:text-rose-400" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-rose-700 dark:text-rose-300">{t('highRiskIntercepted.title')}</p>
            <p className="text-[11px] text-rose-600/80 dark:text-rose-400/80 mt-0.5 break-words">
              {t('highRiskIntercepted.description')}
            </p>
          </div>
        </div>
      )}

      {request.executionIntent && (
        <div className="text-xs text-foreground/90 mb-2 rounded-md border border-border/60 bg-muted/40 px-2.5 py-2">
          <span className="font-medium text-muted-foreground">{t('executionIntent')}:</span> {request.executionIntent}
        </div>
      )}

      {request.reason && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">{t('reason')}:</span> {request.reason}
        </div>
      )}

      {shellCommand ? (
        <ShellCommandDisplay
          toolName={request.toolName}
          command={shellCommand}
          commandSpans={request.commandSpans}
          commandSpanRisks={request.commandSpanRisks}
          commandSpanReasons={request.commandSpanReasons}
          plainExplanation={request.plainExplanation}
          workspaceRoot={request.workspaceRoot}
          scriptOperandPath={request.scriptOperandPath}
          scriptOperandHash={request.scriptOperandHash}
        />
      ) : isSaveSkill ? (
        <SaveSkillApprovalPreview
          toolInput={request.toolInput}
          showFullInstructionsLabel={t('saveSkill.showFullInstructions')}
          showLessLabel={t('saveSkill.showLess')}
          showAllLinesLabel={t('saveSkill.showAllLines')}
          footerText={t('saveSkill.footer')}
        />
      ) : request.diff ? (
        <div className="rounded-lg border overflow-hidden max-h-80 overflow-y-auto">
          <DiffViewer
            diff={request.diff}
            filePath={diffFilePath(request.toolInput)}
            defaultViewMode="unified"
            embedded
            className="text-xs"
          />
        </div>
      ) : hideCompactPayload ? null : (
        inputEntries.length > 0 && (
          <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-xs font-mono">
            {JSON.stringify(Object.fromEntries(inputEntries), null, 2)}
          </pre>
        )
      )}

      {request.domains && request.domains.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <Globe className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
          <span className="text-xs font-medium text-muted-foreground">{t('domain.label')}:</span>
          {request.domains.map((domain) => (
            <Badge
              key={domain}
              variant="outline"
              className="font-mono text-xs text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/30"
            >
              {domain}
            </Badge>
          ))}
        </div>
      )}
    </>
  );
}
