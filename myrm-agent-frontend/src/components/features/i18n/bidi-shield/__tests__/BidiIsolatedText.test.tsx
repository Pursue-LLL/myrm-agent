import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BidiIsolatedText } from '../BidiIsolatedText';
import { WINDOWS_RTL_SAFE_FONT_STACK } from '../bidiDetectorEngine';
import { useBidiShieldStore } from '../useBidiShieldStore';

describe('BidiIsolatedText', () => {
  beforeEach(() => {
    useBidiShieldStore.getState().resetToDefault();
  });

  it('对纯英文或纯中文输入自动探测并渲染为 ltr 容器', () => {
    render(<BidiIsolatedText text="Hello World" />);

    const container = screen.getByTestId('bidi-isolated-container');
    expect(container).toHaveAttribute('dir', 'ltr');
    expect(container).toHaveClass('text-start');
    expect(container).toHaveTextContent('Hello World');
  });

  it('对阿拉伯语输入自动探测并渲染为 rtl 容器', () => {
    render(<BidiIsolatedText text="مرحبا بكم في واجهة الاستخدام" />);

    const container = screen.getByTestId('bidi-isolated-container');
    expect(container).toHaveAttribute('dir', 'rtl');
  });

  it('优先尊重外部显式传入的 dir 属性', () => {
    render(
      <BidiIsolatedText
        text="مرحبا بكم"
        dir="ltr"
      />
    );

    const container = screen.getByTestId('bidi-isolated-container');
    expect(container).toHaveAttribute('dir', 'ltr');
  });

  it('对混合文本中的代码或变量名自动包裹独立 ltr 的 bdi 隔离段', () => {
    render(
      <BidiIsolatedText text="يرجى مراجعة المتغير `user_token` والتأكد من القيمة." />
    );

    const codeSegments = screen.getAllByTestId('bidi-isolated-code-segment');
    expect(codeSegments.length).toBeGreaterThanOrEqual(1);

    const tokenCode = codeSegments.find((seg) =>
      seg.textContent?.includes('`user_token`')
    );
    expect(tokenCode).toBeDefined();
    expect(tokenCode).toHaveAttribute('dir', 'ltr');
  });

  it('开启 Windows 字体防护时容器注入稳健字体回退栈', () => {
    useBidiShieldStore.setState({ isWindowsTypographyShieldActive: true });
    render(<BidiIsolatedText text="مرحبا" />);

    const container = screen.getByTestId('bidi-isolated-container');
    expect(container.style.fontFamily).toBe(WINDOWS_RTL_SAFE_FONT_STACK);
  });

  it('支持自定义 HTML 渲染标签（如 span 或 p）', () => {
    const { container } = render(
      <BidiIsolatedText text="段落文本" as="p" />
    );

    const paragraph = container.querySelector('p');
    expect(paragraph).toBeInTheDocument();
    expect(paragraph).toHaveAttribute('dir', 'ltr');
  });
});
