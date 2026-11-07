'use client';

import React, { Component, ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { redactErrorMessage } from '@/lib/utils/error-handling';

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

interface FallbackProps {
  fallbackMessage?: string;
  error: Error | null;
  onReset: () => void;
}

/** Class components cannot call hooks, so the translated fallback UI lives in its own function component. */
function ArtifactErrorFallback({ fallbackMessage, error, onReset }: FallbackProps) {
  const t = useTranslations('artifacts.errorBoundary');
  return (
    <div className="h-full w-full flex flex-col items-center justify-center p-8 bg-muted/30">
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center">
          <AlertTriangle className="w-8 h-8 text-destructive-text" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-foreground mb-2">{t('title')}</h3>
          <p className="text-sm text-muted-foreground">{fallbackMessage || t('defaultMessage')}</p>
          {error && (
            <p className="text-xs text-destructive-text mt-2 font-mono break-all">
              {redactErrorMessage(error.message)}
            </p>
          )}
        </div>
        <Button variant="outline" onClick={onReset} className="gap-2">
          <RefreshCw className="w-4 h-4" />
          {t('retry')}
        </Button>
      </div>
    </div>
  );
}

/**
 * Artifact 渲染错误边界组件
 * 捕获子组件的渲染错误，显示友好的错误界面
 */
class ArtifactErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ArtifactErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <ArtifactErrorFallback
          fallbackMessage={this.props.fallbackMessage}
          error={this.state.error}
          onReset={this.handleReset}
        />
      );
    }

    return this.props.children;
  }
}

export default ArtifactErrorBoundary;
