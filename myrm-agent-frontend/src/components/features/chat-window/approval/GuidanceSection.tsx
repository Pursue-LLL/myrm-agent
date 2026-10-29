'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: toolApproval.guidance 文案)
 *
 * [OUTPUT]
 * - GuidanceSection: 审批卡里「给 Agent 补充说明」的折叠输入；收起时有内容会显示提示徽标
 *
 * [POS]
 * 受控组件：说明文字和展开状态都由审批卡持有，切到编辑/拒绝视图再回来时不丢。
 */

import { ChevronDown, ChevronRight, MessageSquarePlus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Badge } from '@/components/primitives/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import { Textarea } from '@/components/primitives/textarea';

interface GuidanceSectionProps {
  value: string;
  onChange: (value: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function GuidanceSection({ value, onChange, open, onOpenChange }: GuidanceSectionProps) {
  const t = useTranslations('toolApproval');

  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <MessageSquarePlus className="h-3 w-3" />
          <span>{t('guidance.toggle')}</span>
          {value.trim() && !open && (
            <Badge variant="secondary" className="ml-1 text-[10px] h-4 px-1">
              {t('guidance.hasGuidance')}
            </Badge>
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t('guidance.placeholder')}
          className="min-h-[60px] max-h-[120px] text-xs resize-y"
          rows={2}
        />
        <p className="mt-1 text-[10px] text-muted-foreground">{t('guidance.hint')}</p>
      </CollapsibleContent>
    </Collapsible>
  );
}
