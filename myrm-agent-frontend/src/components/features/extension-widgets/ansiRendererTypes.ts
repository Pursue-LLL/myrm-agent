/**
 * ANSI Renderer and Extension Widgets Domain Types.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure domain types for ANSI parsing tokens, style mappings, and extension widgets.
 * [POS] src/components/features/extension-widgets/ansiRendererTypes.ts
 */

export interface AnsiTokenStyle {
  color?: string;
  backgroundColor?: string;
  fontWeight?: 'normal' | 'bold';
  fontStyle?: 'normal' | 'italic';
  textDecoration?: 'none' | 'underline';
  opacity?: number;
}

export interface AnsiToken {
  text: string;
  style: AnsiTokenStyle;
}

export interface ExtensionWidgetProps {
  id: string;
  title: string;
  className?: string;
  collapsed?: boolean;
  onToggleCollapse?: (id: string) => void;
}

export interface NanoContextData {
  usedTokens: number;
  maxTokens: number;
  percentage: number;
  turnCount: number;
  modelName: string;
}

export interface TodoItem {
  id: string;
  text: string;
  done: boolean;
}
