'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Sparkles, ArrowRight, CheckCircle2, RotateCcw } from 'lucide-react';

export interface TableField {
  field_id: string;
  name: string;
  field_type: string;
}

export interface CellDiffItem {
  row_id: string;
  field_id: string;
  old_value: string;
  new_value: string;
  reasoning?: string;
}

interface BitableSidebarCopilotProps {
  isOpen: boolean;
  onClose: () => void;
  tableName: string;
  fields: TableField[];
  rowCount: number;
  onApplyMutations?: (mutations: CellDiffItem[]) => void;
}

export const BitableSidebarCopilot: React.FC<BitableSidebarCopilotProps> = ({
  isOpen,
  onClose,
  tableName,
  fields,
  rowCount,
  onApplyMutations,
}) => {
  const [prompt, setPrompt] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [diffs, setDiffs] = useState<CellDiffItem[]>([]);
  const [applied, setApplied] = useState(false);

  const handleRunAI = () => {
    if (!prompt.trim()) return;
    setIsProcessing(true);
    setApplied(false);

    // Mock interactive data wrangling synthesis
    setTimeout(() => {
      const generatedDiffs: CellDiffItem[] = [
        {
          row_id: 'row_1',
          field_id: fields[0]?.field_id || 'col_1',
          old_value: '原始用户反馈：系统响应非常迅速',
          new_value: '正面 / Positive',
          reasoning: '检测到正面情绪评价关键词',
        },
        {
          row_id: 'row_2',
          field_id: fields[0]?.field_id || 'col_1',
          old_value: '原始用户反馈：偶尔遇到网络抖动超时',
          new_value: '负面 / Negative',
          reasoning: '提取出网络故障与超时负向特征',
        },
      ];
      setDiffs(generatedDiffs);
      setIsProcessing(false);
    }, 600);
  };

  const handleApply = () => {
    if (onApplyMutations) {
      onApplyMutations(diffs);
    }
    setApplied(true);
  };

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent side="right" className="w-full sm:max-w-md flex flex-col p-6 bg-card text-card-foreground border-l border-border">
        <SheetHeader className="pb-4 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <Sparkles className="w-4 h-4" />
            </div>
            <SheetTitle className="text-base font-semibold">
              Data CoPilot
            </SheetTitle>
          </div>
          <SheetDescription className="text-xs text-muted-foreground">
            当前绑定表格：<span className="font-medium text-foreground">{tableName}</span>（共 {rowCount} 行，{fields.length} 列）
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto py-4 space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">
              自然语言加工指令 / Prompt
            </label>
            <div className="flex gap-2">
              <Input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="例如：根据反馈内容生成情感分类标签..."
                className="text-xs"
                onKeyDown={(e) => e.key === 'Enter' && handleRunAI()}
              />
              <Button
                size="sm"
                onClick={handleRunAI}
                disabled={isProcessing || !prompt.trim()}
                className="gap-1.5 text-xs"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {isProcessing ? '处理中' : '执行'}
              </Button>
            </div>
          </div>

          {diffs.length > 0 && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  变更预览（共 {diffs.length} 处修改）
                </span>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  Ready to Apply
                </Badge>
              </div>

              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {diffs.map((diff, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg border border-border bg-muted/40 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>Row: {diff.row_id}</span>
                      {diff.reasoning && (
                        <span className="text-primary truncate max-w-[180px]">
                          {diff.reasoning}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="line-through text-muted-foreground truncate max-w-[120px]">
                        {diff.old_value || '(空)'}
                      </span>
                      <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />
                      <span className="font-medium text-emerald-600 dark:text-emerald-400 truncate max-w-[140px]">
                        {diff.new_value}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDiffs([])}
                  className="text-xs h-8"
                >
                  <RotateCcw className="w-3.5 h-3.5 mr-1" />
                  清空
                </Button>
                <Button
                  size="sm"
                  onClick={handleApply}
                  disabled={applied}
                  className="text-xs h-8 bg-emerald-600 hover:bg-emerald-700 text-white gap-1.5"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {applied ? '已写回单元格' : '一键写回表格'}
                </Button>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
};
