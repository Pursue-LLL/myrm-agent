'use client';

import React, { Component, ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface UIComponentErrorBoundaryProps {
  children: ReactNode;
  componentType: string;
  componentId: string;
}

interface UIComponentErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * 单组件级 ErrorBoundary，用于 Interactive UI 组件的精细化容错。
 * 捕获单个组件的渲染异常，显示占位符，避免扩散到其他组件。
 *
 * 因 React 要求 ErrorBoundary 必须是 class component，无法直接使用 hooks。
 * 错误文案使用英文，作为异常场景的开发调试辅助信息。
 */
class UIComponentErrorBoundary extends Component<UIComponentErrorBoundaryProps, UIComponentErrorBoundaryState> {
  constructor(props: UIComponentErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): UIComponentErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error(
      `[InteractiveUI] Component "${this.props.componentType}" (id: ${this.props.componentId}) render failed:`,
      error,
      errorInfo,
    );
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive/80">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>
            Component &quot;{this.props.componentType}&quot; render failed
            {this.state.error && `: ${this.state.error.message}`}
          </span>
        </div>
      );
    }

    return this.props.children;
  }
}

export default UIComponentErrorBoundary;
