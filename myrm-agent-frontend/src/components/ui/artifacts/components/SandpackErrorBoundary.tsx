/**
 * Sandpack错误边界组件
 */

import React, { useState, useEffect } from 'react';
import { useSandpack } from '@codesandbox/sandpack-react';
import { AlertCircle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CompileErrorDisplay } from './CompileErrorDisplay';

interface SandpackErrorBoundaryProps {
  children: React.ReactNode;
  labels: {
    renderError: string;
    renderErrorHint: string;
    retry: string;
  };
}

export const SandpackErrorBoundary = ({ children, labels }: SandpackErrorBoundaryProps) => {
  const { sandpack } = useSandpack();
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (sandpack.status === 'timeout' || sandpack.status === 'idle') {
      setHasError(true);
    } else {
      setHasError(false);
    }
  }, [sandpack.status]);

  // 检查是否有编译错误
  const bundlerErrors = sandpack.error;
  if (bundlerErrors) {
    return <CompileErrorDisplay error={bundlerErrors.message} onRetry={() => sandpack.runSandpack()} labels={labels} />;
  }

  if (hasError) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4 p-6 text-center">
        <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-destructive" />
        </div>
        <div>
          <p className="font-medium text-foreground">{labels.renderError}</p>
          <p className="text-sm text-muted-foreground mt-1">{labels.renderErrorHint}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => sandpack.runSandpack()} className="gap-2">
          <RotateCcw className="w-4 h-4" />
          {labels.retry}
        </Button>
      </div>
    );
  }

  return <>{children}</>;
};
