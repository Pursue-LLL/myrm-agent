import { describe, expect, it } from 'vitest';
import {
  THEME_DEFINITIONS,
  buildSafeSandboxIframeSrcDoc,
  bundleSingleFileOfflineHtml,
  calculateFinancialSandplay,
  compileInlinedHtml,
  recordToStyleString,
} from '../artifactSandboxEngine';
import type { FinancialSandplayMetrics } from '../artifactSandboxTypes';

describe('artifactSandboxEngine', () => {
  it('正确将样式对象转为 CSS 样式字符串', () => {
    const styleObj = {
      fontSize: '16px',
      backgroundColor: '#f0fdf4',
      borderBottom: '2px solid green',
    };
    const css = recordToStyleString(styleObj);
    expect(css).toContain('font-size: 16px;');
    expect(css).toContain('background-color: #f0fdf4;');
    expect(css).toContain('border-bottom: 2px solid green;');
  });

  it('编译带多主题内联 CSS 的富文本 HTML', () => {
    const raw =
      '<h1>标题</h1><p>正文段落</p><blockquote>重要引用</blockquote><pre>代码</pre><table><tr><td>表格</td></tr></table>';
    const compiledMint = compileInlinedHtml(raw, 'mint_breeze');
    expect(compiledMint).toContain('<h1 style="');
    expect(compiledMint).toContain('color: #065f46;');
    expect(compiledMint).toContain('<blockquote style="');
    expect(compiledMint).toContain('border-left: 4px solid #10b981;');

    const compiledNoir = compileInlinedHtml(raw, 'executive_noir');
    expect(compiledNoir).toContain('font-family: Georgia, "Times New Roman", serif;');
    expect(compiledNoir).toContain('color: #0f172a;');
  });

  it('构建安全隔离沙盒 iframe srcDoc 文档', () => {
    const srcDoc = buildSafeSandboxIframeSrcDoc('<h1>测试沙盒</h1>');
    expect(srcDoc).toContain('<!DOCTYPE html>');
    expect(srcDoc).toContain('<meta charset="utf-8">');
    expect(srcDoc).toContain('<h1>测试沙盒</h1>');
  });

  it('打包单文件离线 HTML 并将素材转为内联 Base64 Data URI', () => {
    const rawHtml = '<img src="sample.png" /><div>背景图: bg.jpg</div>';
    const assets = [
      { name: 'sample.png', mimeType: 'image/png', base64: 'iVBORw0KGgo' },
      { name: 'bg.jpg', mimeType: 'image/jpeg', base64: '9j4AAQSkZJRg' },
    ];
    const bundled = bundleSingleFileOfflineHtml(rawHtml, assets);
    expect(bundled).toContain('data:image/png;base64,iVBORw0KGgo');
    expect(bundled).toContain('data:image/jpeg;base64,9j4AAQSkZJRg');
    expect(bundled).not.toContain('sample.png');
  });

  it('金融沙盘指标因果推演与宏观冲击情景测算', () => {
    const base: FinancialSandplayMetrics = {
      upstreamRawMaterialCost: 100,
      midstreamProcessingCapacity: 80,
      downstreamEndUserDemand: 120,
      projectedProfitMargin: 0,
      systemicRiskIndex: 0,
    };

    const calculated = calculateFinancialSandplay(base);
    expect(calculated.projectedProfitMargin).toBe(12.4); // 120*0.12(14.4) + 80*0.15(12) - 100*0.14(14) = 12.4
    expect(calculated.systemicRiskIndex).toBe(43); // 100*0.3(30) + 20*0.35(7) + 30*0.2(6) = 43

    // 注入原材料短缺冲击
    const shocked = calculateFinancialSandplay(base, {
      id: 'shock-1',
      name: '短缺冲击',
      description: '上游成本提升',
      impactDeltas: {
        upstreamRawMaterialCost: 30,
        midstreamProcessingCapacity: -10,
      },
    });

    expect(shocked.upstreamRawMaterialCost).toBe(130);
    expect(shocked.midstreamProcessingCapacity).toBe(70);
    expect(shocked.projectedProfitMargin).toBeLessThan(calculated.projectedProfitMargin);
    expect(shocked.systemicRiskIndex).toBeGreaterThan(calculated.systemicRiskIndex);
  });
});
