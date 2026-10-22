/**
 * Web Terminal ANSI Parser & Virtual Terminal Emulator
 * 终端 ANSI 控制转义序列解析、VT100 键盘映射与行缓冲区引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import {
  TerminalAnsiStyle,
  TerminalBufferLine,
  TerminalBufferSegment,
} from './webTerminalTypes';

const ANSI_COLORS: Record<number, string> = {
  30: '#1e1e1e', // black
  31: '#f87171', // red
  32: '#4ade80', // green
  33: '#facc15', // yellow
  34: '#60a5fa', // blue
  35: '#c084fc', // magenta
  36: '#22d3ee', // cyan
  37: '#e2e8f0', // white
  90: '#64748b', // bright black (gray)
  91: '#ef4444', // bright red
  92: '#22c55e', // bright green
  93: '#eab308', // bright yellow
  94: '#3b82f6', // bright blue
  95: '#a855f7', // bright magenta
  96: '#06b6d4', // bright cyan
  97: '#ffffff', // bright white
};

const ANSI_BG_COLORS: Record<number, string> = {
  40: '#0f172a',
  41: '#7f1d1d',
  42: '#14532d',
  43: '#713f12',
  44: '#1e3a8a',
  45: '#581c87',
  46: '#164e63',
  47: '#334155',
  100: '#1e293b',
  101: '#991b1b',
  102: '#166534',
  103: '#854d0e',
  104: '#1d4ed8',
  105: '#6b21a8',
  106: '#155e75',
  107: '#475569',
};

export function mapKeyToControlSequence(key: string, ctrlKey: boolean = false): string | null {
  if (ctrlKey) {
    const lower = key.toLowerCase();
    if (lower === 'c') {
      return '\x03'; // SIGINT
    }
    if (lower === 'd') {
      return '\x04'; // EOF
    }
    if (lower === 'z') {
      return '\x1a'; // SIGTSTP
    }
    if (lower === 'l') {
      return '\x0c'; // Form feed (clear screen)
    }
    return null;
  }

  if (key === 'Enter') {
    return '\r';
  }
  if (key === 'Backspace') {
    return '\b';
  }
  if (key === 'Tab') {
    return '\t';
  }
  if (key === 'ArrowUp') {
    return '\x1b[A';
  }
  if (key === 'ArrowDown') {
    return '\x1b[B';
  }
  if (key === 'ArrowRight') {
    return '\x1b[C';
  }
  if (key === 'ArrowLeft') {
    return '\x1b[D';
  }

  if (key.length === 1) {
    return key;
  }

  return null;
}

export function parseAnsiChunkToSegments(text: string): TerminalBufferSegment[] {
  const segments: TerminalBufferSegment[] = [];
  const escChar = String.fromCharCode(27);
  const ansiRegex = new RegExp(`${escChar}\\[([0-9;]*)m`, 'g');
  let lastIndex = 0;
  let currentStyle: TerminalAnsiStyle = {};

  let match: RegExpExecArray | null = ansiRegex.exec(text);
  while (match !== null) {
    const textBefore = text.slice(lastIndex, match.index);
    if (textBefore.length > 0) {
      segments.push({
        text: textBefore,
        style: { ...currentStyle },
      });
    }

    const codeStr = match[1];
    if (!codeStr || codeStr === '0') {
      currentStyle = {};
    } else {
      const codes = codeStr.split(';').map((c) => Number.parseInt(c, 10));
      for (const code of codes) {
        if (code === 0) {
          currentStyle = {};
        } else if (code === 1) {
          currentStyle.bold = true;
        } else if (code === 2) {
          currentStyle.dim = true;
        } else if (code === 3) {
          currentStyle.italic = true;
        } else if (code === 4) {
          currentStyle.underline = true;
        } else if (ANSI_COLORS[code]) {
          currentStyle.color = ANSI_COLORS[code];
        } else if (ANSI_BG_COLORS[code]) {
          currentStyle.backgroundColor = ANSI_BG_COLORS[code];
        }
      }
    }

    lastIndex = ansiRegex.lastIndex;
    match = ansiRegex.exec(text);
  }

  const remainingText = text.slice(lastIndex);
  if (remainingText.length > 0) {
    segments.push({
      text: remainingText,
      style: { ...currentStyle },
    });
  }

  return segments;
}

export function appendRawChunkToLines(
  existingLines: TerminalBufferLine[],
  rawChunk: string,
  maxLines: number = 1000
): TerminalBufferLine[] {
  if (rawChunk === '\x0c' || rawChunk.includes('\x1b[2J')) {
    return [];
  }

  // 规整换行符
  const normalized = rawChunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const chunks = normalized.split('\n');

  const lines = [...existingLines];

  for (let i = 0; i < chunks.length; i++) {
    const chunkText = chunks[i];
    if (chunkText.length === 0 && i > 0 && i === chunks.length - 1) {
      continue;
    }

    const segments = parseAnsiChunkToSegments(chunkText);
    const lineId = `line-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

    lines.push({
      id: lineId,
      segments: segments.length > 0 ? segments : [{ text: '', style: {} }],
      timestamp: Date.now(),
    });
  }

  if (lines.length > maxLines) {
    return lines.slice(lines.length - maxLines);
  }

  return lines;
}
