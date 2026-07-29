/**
 * [INPUT]
 * - lucide-react 图标组件（POS: 快捷操作视觉提示）
 *
 * [OUTPUT]
 * - FlowPadQuickActions: 截图场景快捷动作条。
 *
 * [POS]
 * FlowPad 快捷操作子组件，承载 reply/summarize/translate/explain 四类高频动作，
 * 通过受控 props 与主组件解耦，降低主文件复杂度。
 */
import { FileText, Languages, Lightbulb, MessageSquareReply } from 'lucide-react';

type FlowPadQuickActionKey = 'replyPrompt' | 'summarizePrompt' | 'translatePrompt' | 'explainPrompt';

interface FlowPadQuickActionsProps {
  disabled: boolean;
  onQuickAction: (key: FlowPadQuickActionKey) => void;
  t: (key: string) => string;
}

const QUICK_ACTIONS: Array<{
  key: FlowPadQuickActionKey;
  labelKey: string;
  Icon: typeof MessageSquareReply;
}> = [
  { key: 'replyPrompt', labelKey: 'quickReply', Icon: MessageSquareReply },
  { key: 'summarizePrompt', labelKey: 'quickSummarize', Icon: FileText },
  { key: 'translatePrompt', labelKey: 'quickTranslate', Icon: Languages },
  { key: 'explainPrompt', labelKey: 'quickExplain', Icon: Lightbulb },
];

export function FlowPadQuickActions({ disabled, onQuickAction, t }: FlowPadQuickActionsProps) {
  return (
    <div className="px-4 py-2 border-b border-border/20 flex flex-wrap gap-1.5">
      {QUICK_ACTIONS.map(({ key, labelKey, Icon }) => (
        <button
          key={key}
          type="button"
          disabled={disabled}
          onClick={() => onQuickAction(key)}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full border border-border/50 bg-background hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
        >
          <Icon className="w-3 h-3" />
          {t(labelKey)}
        </button>
      ))}
    </div>
  );
}
