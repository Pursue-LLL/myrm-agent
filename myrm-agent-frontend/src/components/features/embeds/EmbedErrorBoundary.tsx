'use client';

import React from 'react';

interface Props {
  children: React.ReactNode;
  fallback: React.ReactNode;
  resetKey?: string;
}

interface State {
  hasError: boolean;
  resetKey?: string;
}

export class EmbedErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(): Partial<State> {
    return { hasError: true };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (props.resetKey !== state.resetKey) {
      return { hasError: false, resetKey: props.resetKey };
    }
    return null;
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}
