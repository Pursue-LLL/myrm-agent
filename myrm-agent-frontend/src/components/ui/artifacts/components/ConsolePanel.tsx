/**
 * 控制台面板组件
 */

import { memo } from 'react';
import { Terminal, ChevronDown, ChevronUp, X } from 'lucide-react';
import { SandpackConsole } from '@codesandbox/sandpack-react';
import { Button } from '@/components/ui/button';

/**
 * ConsolePanel 组件参数类型
 */
interface ConsolePanelProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  label: string;
}

const ConsolePanel = ({ isOpen, onToggle, onClose, label }: ConsolePanelProps) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="border-t border-border bg-muted/30">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/50">
        <button
          onClick={onToggle}
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <Terminal className="w-3.5 h-3.5" />
          {label}
          {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
        </button>
        <Button variant="ghost" size="icon" className="w-6 h-6" onClick={onClose}>
          <X className="w-3.5 h-3.5" />
        </Button>
      </div>
      <div className="h-32 overflow-auto">
        <SandpackConsole showHeader={false} className="h-full" resetOnPreviewRestart />
      </div>
    </div>
  );
};

/**
 * 性能优化：使用 React.memo
 * 仅在 props 变化时重新渲染
 */
export default memo(ConsolePanel);
