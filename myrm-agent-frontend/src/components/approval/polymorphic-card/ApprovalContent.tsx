'use client';

import { useTranslations } from 'next-intl';
import { OutboundDraftApprovalBody } from '@/components/approval/OutboundDraftApprovalBody';
import type { ApprovalPayload } from '@/store/useApprovalStore';
import { BatchCostApprovalContent } from './BatchCostApprovalContent';
import { HighRiskDomActionContent } from './HighRiskDomActionContent';
import { KnowledgePatchContent } from './KnowledgePatchContent';
import { McpElicitationContent } from './McpElicitationContent';
import { SkillApprovalContent } from './SkillApprovalContent';
import { SubagentApprovalContent } from './SubagentApprovalContent';
import { ToolClarificationContent } from './ToolClarificationContent';

function PayloadText({ title, text }: { title: string; text: string }) {
  return (
    <div className="space-y-4">
      <h4 className="font-medium text-sm text-muted-foreground">{title}</h4>
      <div className="rounded-lg bg-muted p-4 font-mono text-sm whitespace-pre-wrap overflow-x-auto">{text}</div>
    </div>
  );
}

interface ApprovalContentProps {
  approval: ApprovalPayload;
  /** The tool-clarification editor's text, owned by the card because approving sends it. */
  editedArgs: string;
  onEditedArgsChange: (value: string) => void;
}

/** The body of an approval card: the review layout that fits the approval's action type. */
export function ApprovalContent({ approval, editedArgs, onEditedArgsChange }: ApprovalContentProps) {
  const t = useTranslations('toolApproval');

  switch (approval.action_type) {
    case 'subagent_approval':
      return <SubagentApprovalContent approval={approval} />;
    case 'skill_draft':
    case 'skill_patch':
      return (
        <SkillApprovalContent
          reason={approval.reason}
          content={approval.payload?.content || approval.payload?.patch_content}
          originalContent={approval.payload?.original_content}
          language="markdown"
          label={t('skillGrowthPending')}
          viewChangesLabel={t('viewChanges')}
          hideChangesLabel={t('hideChanges')}
        />
      );
    case 'tool_clarification':
      return (
        <ToolClarificationContent approval={approval} editedArgs={editedArgs} onEditedArgsChange={onEditedArgsChange} />
      );
    case 'semantic_memory':
      return (
        <PayloadText
          title={t('memoryUpdate')}
          text={approval.payload?.content || approval.payload?.patch_content || t('noContent')}
        />
      );
    case 'knowledge_patch':
      return <KnowledgePatchContent approval={approval} />;
    case 'batch_cost_approval':
      return <BatchCostApprovalContent approval={approval} />;
    case 'high_risk_dom_action':
      return <HighRiskDomActionContent approval={approval} />;
    case 'outbound_draft':
      return <OutboundDraftApprovalBody payload={approval.payload} />;
    case 'mcp_elicitation':
      return <McpElicitationContent approval={approval} />;
    default:
      return <PayloadText title={t('payloadData')} text={JSON.stringify(approval.payload, null, 2)} />;
  }
}
