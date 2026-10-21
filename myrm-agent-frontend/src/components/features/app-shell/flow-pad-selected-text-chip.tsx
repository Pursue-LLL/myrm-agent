/**
 * [INPUT]
 * - selectedText (POS: Appshot 抽取的选中文本)
 *
 * [OUTPUT]
 * - FlowPadSelectedTextChip: 选中文本提示条。
 *
 * [POS]
 * FlowPad 选中文本展示子组件。将截断与样式逻辑从主组件剥离，降低主文件复杂度。
 */
import { TextSelect } from 'lucide-react';

interface FlowPadSelectedTextChipProps {
  selectedText: string;
}

export function FlowPadSelectedTextChip({ selectedText }: FlowPadSelectedTextChipProps) {
  return (
    <div className="px-4 py-2 border-b border-border/30">
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-primary/8 border border-primary/15">
        <TextSelect className="w-3.5 h-3.5 text-primary shrink-0" />
        <span className="text-xs font-medium text-primary/80 truncate">
          {selectedText.length > 80 ? `${selectedText.slice(0, 80)}...` : selectedText}
        </span>
      </div>
    </div>
  );
}
