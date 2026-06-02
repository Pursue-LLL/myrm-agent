/**
 * 编译错误显示组件
 */

import { AlertTriangle, RotateCcw, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface CompileErrorDisplayProps {
  error: string;
  onRetry: () => void;
  labels: {
    renderError: string;
    renderErrorHint: string;
    retry: string;
  };
}

/**
 * 解析错误信息，提取行号和描述
 */
function parseError(errorMsg: string) {
  const lineMatch = errorMsg.match(/\((\d+):(\d+)\)/);
  const line = lineMatch ? parseInt(lineMatch[1], 10) : null;
  const column = lineMatch ? parseInt(lineMatch[2], 10) : null;

  // 提取主要错误信息
  const mainError = errorMsg.split('\n')[0] || errorMsg;

  return { line, column, mainError, fullError: errorMsg };
}

export const CompileErrorDisplay = ({ error, onRetry, labels }: CompileErrorDisplayProps) => {
  const { line, column, mainError } = parseError(error);

  return (
    <div className="h-full flex flex-col bg-destructive/5 p-4 overflow-auto">
      <div className="flex items-start gap-3 mb-4">
        <div className="w-10 h-10 rounded-lg bg-destructive/10 flex items-center justify-center flex-shrink-0">
          <AlertTriangle className="w-5 h-5 text-destructive" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-destructive text-sm">{labels.renderError}</h4>
          {line && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Line {line}
              {column ? `, Column ${column}` : ''}
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={onRetry} className="flex-shrink-0 gap-1.5">
          <RotateCcw className="w-3.5 h-3.5" />
          {labels.retry}
        </Button>
      </div>

      <div className="flex-1 bg-background rounded-lg border border-destructive/20 p-3 overflow-auto">
        <pre className="text-xs text-destructive/90 whitespace-pre-wrap font-mono">{mainError}</pre>
      </div>

      <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
        <Info className="w-3.5 h-3.5" />
        <span>{labels.renderErrorHint}</span>
      </div>
    </div>
  );
};
