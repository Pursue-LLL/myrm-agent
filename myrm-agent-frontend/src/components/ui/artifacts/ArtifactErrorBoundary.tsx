'use client';

import React, { Component, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
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
        <div className="h-full w-full flex flex-col items-center justify-center p-8 bg-muted/30">
          <div className="flex flex-col items-center gap-4 max-w-md text-center">
            <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-destructive" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-2">渲染出错</h3>
              <p className="text-sm text-muted-foreground">
                {this.props.fallbackMessage || '无法渲染该内容，请尝试刷新或下载查看'}
              </p>
              {this.state.error && (
                <p className="text-xs text-destructive/80 mt-2 font-mono break-all">{this.state.error.message}</p>
              )}
            </div>
            <Button variant="outline" onClick={this.handleReset} className="gap-2">
              <RefreshCw className="w-4 h-4" />
              重试
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ArtifactErrorBoundary;
