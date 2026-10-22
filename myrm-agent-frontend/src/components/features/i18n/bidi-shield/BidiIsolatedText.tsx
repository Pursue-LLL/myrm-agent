/**
 * Bidi Isolated Text Component
 * 全球化双向文本自动隔离排版与 CSS 逻辑属性渲染组件
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 强制应用 <bdi> 双向隔离标签与 unicode-bidi: isolate；
 * 5. 行数严格受控在 200 行以内。
 */

import React, { useMemo } from 'react';
import {
  detectTextDirection,
  WINDOWS_RTL_SAFE_FONT_STACK,
} from './bidiDetectorEngine';
import { TextDirection } from './bidiShieldTypes';
import { useBidiShieldStore } from './useBidiShieldStore';

export interface BidiIsolatedTextProps {
  text: string;
  dir?: TextDirection;
  className?: string;
  as?: 'div' | 'p' | 'span';
}

export const BidiIsolatedText: React.FC<BidiIsolatedTextProps> = ({
  text,
  dir,
  className = '',
  as: Component = 'div',
}) => {
  const { isWindowsTypographyShieldActive } = useBidiShieldStore();

  const detection = useMemo(() => {
    return detectTextDirection(text);
  }, [text]);

  const effectiveDir: 'ltr' | 'rtl' = useMemo(() => {
    if (dir === 'rtl') {
      return 'rtl';
    }
    if (dir === 'ltr') {
      return 'ltr';
    }
    return detection.dominantDirection;
  }, [dir, detection.dominantDirection]);

  const fontStyle = isWindowsTypographyShieldActive
    ? { fontFamily: WINDOWS_RTL_SAFE_FONT_STACK }
    : undefined;

  return (
    <Component
      data-testid="bidi-isolated-container"
      dir={effectiveDir}
      style={fontStyle}
      className={`bidi-isolated-content text-start [unicode-bidi:isolate] ${className}`}
    >
      {detection.segments.map((segment, index) => {
        if (segment.isCodeOrVariable) {
          return (
            <bdi
              key={`${index}-${segment.text}`}
              dir="ltr"
              data-testid="bidi-isolated-code-segment"
              className="inline-block mx-0.5 rounded bg-neutral-800 px-1 py-0.2 font-mono text-[11px] text-indigo-300 [unicode-bidi:isolate]"
            >
              {segment.text}
            </bdi>
          );
        }

        return (
          <bdi
            key={`${index}-${segment.text.slice(0, 10)}`}
            dir={segment.isRtl ? 'rtl' : 'ltr'}
            className="[unicode-bidi:isolate]"
          >
            {segment.text}
          </bdi>
        );
      })}
    </Component>
  );
};
