/**
 * Lightweight, zero-dependency ANSI escape code parser.
 *
 * [INPUT] Raw string containing ANSI SGR codes
 * [OUTPUT] Array of styled AnsiTokens for React rendering
 * [POS] src/components/features/extension-widgets/ansiParser.ts
 */

import type { AnsiToken, AnsiTokenStyle } from './ansiRendererTypes';

// Standard 16 ANSI colors
const ANSI_FOREGROUND_COLORS: Record<number, string> = {
  30: '#1e1e1e', // Black
  31: '#f87171', // Red
  32: '#4ade80', // Green
  33: '#facc15', // Yellow
  34: '#60a5fa', // Blue
  35: '#c084fc', // Magenta
  36: '#38bdf8', // Cyan
  37: '#e2e8f0', // White
  90: '#64748b', // Bright Black (Gray)
  91: '#ef4444', // Bright Red
  92: '#22c55e', // Bright Green
  93: '#eab308', // Bright Yellow
  94: '#3b82f6', // Bright Blue
  95: '#a855f7', // Bright Magenta
  96: '#06b6d4', // Bright Cyan
  97: '#ffffff', // Bright White
};

const ANSI_BACKGROUND_COLORS: Record<number, string> = {
  40: '#000000',
  41: '#7f1d1d',
  42: '#14532d',
  43: '#713f12',
  44: '#1e3a8a',
  45: '#581c87',
  46: '#164e63',
  47: '#cbd5e1',
  100: '#334155',
  101: '#991b1b',
  102: '#166534',
  103: '#854d0e',
  104: '#1d4ed8',
  105: '#6b21a8',
  106: '#0e7490',
  107: '#f8fafc',
};

// 256-color palette lookup helper
function get256Color(n: number): string {
  if (n < 16) {
    return ANSI_FOREGROUND_COLORS[30 + (n % 8)] || '#cbd5e1';
  }
  if (n >= 232) {
    // Grayscale ramp
    const gray = Math.round(((n - 232) / 23) * 255);
    return `rgb(${gray}, ${gray}, ${gray})`;
  }
  // 6x6x6 color cube
  const adjusted = n - 16;
  const r = Math.floor(adjusted / 36);
  const g = Math.floor((adjusted % 36) / 6);
  const b = adjusted % 6;
  const toRgb = (v: number) => (v === 0 ? 0 : 55 + v * 40);
  return `rgb(${toRgb(r)}, ${toRgb(g)}, ${toRgb(b)})`;
}

/**
 * Parse an ANSI-formatted string into typed tokens
 */
export function parseAnsiString(input: string): AnsiToken[] {
  if (!input) {
    return [];
  }

  // Regex to match ANSI escape sequences: \x1b[...m or \u001b[...m
  // eslint-disable-next-line no-control-regex
  const ansiRegex = /(?:\u001b|(?:\x1b))\[([0-9;]*)m/g;
  const tokens: AnsiToken[] = [];

  let currentStyle: AnsiTokenStyle = {};
  let lastIndex = 0;
  let match: RegExpExecArray | null = ansiRegex.exec(input);

  while (match !== null) {
    const textSegment = input.slice(lastIndex, match.index);
    if (textSegment.length > 0) {
      tokens.push({
        text: textSegment,
        style: { ...currentStyle },
      });
    }

    const codeStr = match[1];
    const codes = codeStr.length > 0 ? codeStr.split(';').map(Number) : [0];

    let i = 0;
    while (i < codes.length) {
      const code = codes[i];

      if (code === 0) {
        // Reset all styles
        currentStyle = {};
      } else if (code === 1) {
        currentStyle.fontWeight = 'bold';
      } else if (code === 2) {
        currentStyle.opacity = 0.6;
      } else if (code === 3) {
        currentStyle.fontStyle = 'italic';
      } else if (code === 4) {
        currentStyle.textDecoration = 'underline';
      } else if (code === 22) {
        currentStyle.fontWeight = 'normal';
        currentStyle.opacity = 1.0;
      } else if (code === 23) {
        currentStyle.fontStyle = 'normal';
      } else if (code === 24) {
        currentStyle.textDecoration = 'none';
      } else if (code >= 30 && code <= 37) {
        currentStyle.color = ANSI_FOREGROUND_COLORS[code];
      } else if (code === 39) {
        delete currentStyle.color;
      } else if (code >= 40 && code <= 47) {
        currentStyle.backgroundColor = ANSI_BACKGROUND_COLORS[code];
      } else if (code === 49) {
        delete currentStyle.backgroundColor;
      } else if (code >= 90 && code <= 97) {
        currentStyle.color = ANSI_FOREGROUND_COLORS[code];
      } else if (code >= 100 && code <= 107) {
        currentStyle.backgroundColor = ANSI_BACKGROUND_COLORS[code];
      } else if (code === 38 && codes[i + 1] === 5 && codes[i + 2] !== undefined) {
        // 256 foreground: 38;5;n
        currentStyle.color = get256Color(codes[i + 2]);
        i += 2;
      } else if (code === 48 && codes[i + 1] === 5 && codes[i + 2] !== undefined) {
        // 256 background: 48;5;n
        currentStyle.backgroundColor = get256Color(codes[i + 2]);
        i += 2;
      }

      i++;
    }

    lastIndex = ansiRegex.lastIndex;
    match = ansiRegex.exec(input);
  }

  // Trailing text segment
  const remainingText = input.slice(lastIndex);
  if (remainingText.length > 0) {
    tokens.push({
      text: remainingText,
      style: { ...currentStyle },
    });
  }

  return tokens;
}
