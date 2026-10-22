import { describe, it, expect } from 'vitest';
import {
  DEFAULT_DEV_LEXICON,
  extractContextTerms,
  correctSpeechTranscript,
  detectAndFormatCodeSymbols,
} from '../speechBiasEngine';

describe('speechBiasEngine', () => {
  it('默认技术术语词典包含核心高频误听开发工具', () => {
    const terms = DEFAULT_DEV_LEXICON.map((item) => item.term);
    expect(terms).toContain('grep');
    expect(terms).toContain('pnpm');
    expect(terms).toContain('Kubernetes');
    expect(terms).toContain('docker');
    expect(terms).toContain('tmux');
    expect(terms).toContain('vitest');
    expect(terms).toContain('oxlint');
  });

  it('正确从当前分支、AST 符号和技能中提取上下文偏置词典', () => {
    const extracted = extractContextTerms({
      branch: 'feature/auth-provider',
      astSymbols: ['handleUserSession', 'AuthTokenValidator'],
      skills: ['chrome-devtools', 'cloudflare'],
      packages: ['lodash-es', 'zod'],
    });

    expect(extracted.length).toBe(7);
    const branchItem = extracted.find((e) => e.category === 'git_branch');
    expect(branchItem).toBeDefined();
    expect(branchItem?.term).toBe('feature/auth-provider');
    expect(branchItem?.aliases).toContain('feature auth provider');

    const astItem = extracted.find((e) => e.term === 'handleUserSession');
    expect(astItem).toBeDefined();
    expect(astItem?.category).toBe('ast_symbol');

    const skillItem = extracted.find((e) => e.term === 'chrome-devtools');
    expect(skillItem).toBeDefined();
    expect(skillItem?.category).toBe('skill');
  });

  it('智能纠偏英文误听词与中文同音误听词', () => {
    const input = '请帮我用 grape 查找一下，然后用 pen pm run test，部署到 库伯拉提斯';
    const result = correctSpeechTranscript(input, DEFAULT_DEV_LEXICON);

    expect(result.correctedText).toContain('grep');
    expect(result.correctedText).toContain('pnpm');
    expect(result.correctedText).toContain('Kubernetes');
    expect(result.corrections.length).toBe(3);

    const grepCorr = result.corrections.find((c) => c.corrected === 'grep');
    expect(grepCorr?.original).toBe('grape');
    expect(grepCorr?.category).toBe('cli_tool');

    const pnpmCorr = result.corrections.find((c) => c.corrected === 'pnpm');
    expect(pnpmCorr?.original).toBe('pen pm');

    const k8sCorr = result.corrections.find((c) => c.corrected === 'Kubernetes');
    expect(k8sCorr?.original).toBe('库伯拉提斯');
  });

  it('智能识别驼峰变量与下划线命名并自动包裹代码反引号', () => {
    const raw = '修改 getUserProfile 函数以及 process_batch_items 脚本';
    const formatted = detectAndFormatCodeSymbols(raw);

    expect(formatted).toBe('修改 `getUserProfile` 函数以及 `process_batch_items` 脚本');
  });

  it('空文本输入时平稳降级处理', () => {
    const emptyResult = correctSpeechTranscript('', DEFAULT_DEV_LEXICON);
    expect(emptyResult.correctedText).toBe('');
    expect(emptyResult.corrections.length).toBe(0);

    const symbolResult = detectAndFormatCodeSymbols('');
    expect(symbolResult).toBe('');
  });
});
