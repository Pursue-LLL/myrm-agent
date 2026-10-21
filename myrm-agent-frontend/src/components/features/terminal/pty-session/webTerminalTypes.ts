/**
 * Interactive Web Terminal & Detachable PTY Session Types
 * Web 虚拟终端仿真、持久化 PTY 会话流与键盘控制转义类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 规范定义 ANSI 样式片段、屏幕行缓冲区与 PTY 声明周期状态机；
 * 3. 行数严格受控在 400 行以内。
 */

export type PtySessionStatus =
  | 'connecting'
  | 'connected'
  | 'detached'
  | 'reconnecting'
  | 'terminated'
  | 'error';

export interface PtySessionDescriptor {
  id: string;
  title: string;
  pid: number;
  cwd: string;
  shell: string;
  cols: number;
  rows: number;
  status: PtySessionStatus;
  createdAt: string;
  lastActiveAt: string;
  isDetached: boolean;
  exitCode?: number;
}

export interface TerminalAnsiStyle {
  color?: string; // CSS color string or class
  backgroundColor?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

export interface TerminalBufferSegment {
  text: string;
  style: TerminalAnsiStyle;
}

export interface TerminalBufferLine {
  id: string;
  segments: TerminalBufferSegment[];
  timestamp: number;
}

export interface TerminalDimensions {
  cols: number;
  rows: number;
}

export interface TerminalInputPayload {
  sessionId: string;
  data: string;
  isControlCode?: boolean;
}
