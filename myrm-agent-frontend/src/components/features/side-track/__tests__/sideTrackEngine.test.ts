import { describe, it, expect } from 'vitest';
import {
  generateForkedSnapshot,
  generatePresetInquiries,
  buildSideTrackSystemPrompt,
  createSideTrackSession,
  generateLocalExplainerAnswer,
} from '../sideTrackEngine';
import { ReadOnlyCodeSnapshot, ReadOnlyStepSnapshot } from '../sideTrackTypes';

describe('sideTrackEngine', () => {
  const mockStep: ReadOnlyStepSnapshot = {
    stepId: 'step-01',
    stepTitle: 'AST 并发解析与符号表构建',
    toolAction: 'ast_parse_symbols',
    outputSummary: '成功抽取 128 个符号定义',
    durationMs: 340,
  };

  const mockCode: ReadOnlyCodeSnapshot = {
    filePath: 'src/core/parser.ts',
    codeSnippet: 'export function parseSymbols(input: string): SymbolTable { ... }',
    language: 'typescript',
    startLine: 1,
    endLine: 45,
  };

  it('generates forked snapshot with correct read-only metadata', () => {
    const snapshot = generateForkedSnapshot(
      'main-sess-9988',
      '全栈应用代码重构任务',
      mockStep,
      [mockCode],
      'feature/ast'
    );

    expect(snapshot.mainSessionId).toBe('main-sess-9988');
    expect(snapshot.mainTaskName).toBe('全栈应用代码重构任务');
    expect(snapshot.branchName).toBe('feature/ast');
    expect(snapshot.isUncommittedWorktree).toBe(true);
    expect(snapshot.activeStep?.toolAction).toBe('ast_parse_symbols');
    expect(snapshot.codeSnapshots).toHaveLength(1);
    expect(snapshot.codeSnapshots[0].filePath).toBe('src/core/parser.ts');
  });

  it('generates preset inquiry chips based on step and code snapshots', () => {
    const inquiries = generatePresetInquiries(mockStep, [mockCode]);
    expect(inquiries.length).toBeGreaterThanOrEqual(3);
    expect(inquiries.some((inq) => inq.includes('ast_parse_symbols'))).toBe(true);
    expect(inquiries.some((inq) => inq.includes('src/core/parser.ts'))).toBe(true);
  });

  it('generates fallback preset inquiries when no step or code provided', () => {
    const inquiries = generatePresetInquiries();
    expect(inquiries.length).toBeGreaterThanOrEqual(2);
    expect(inquiries.some((inq) => inq.includes('整体架构设计'))).toBe(true);
  });

  it('builds clear read-only system prompt isolating main task context', () => {
    const snapshot = generateForkedSnapshot(
      'main-sess-1122',
      '数据库微服务拆分',
      mockStep,
      [mockCode]
    );

    const prompt = buildSideTrackSystemPrompt(snapshot);
    expect(prompt).toContain('数据库微服务拆分');
    expect(prompt).toContain('AST 并发解析与符号表构建');
    expect(prompt).toContain('src/core/parser.ts');
    expect(prompt).toContain('零上下文污染');
    expect(prompt).toContain('严禁修改代码');
  });

  it('creates complete side track session with welcome message', () => {
    const session = createSideTrackSession(
      'main-sess-3344',
      '秒级代码生成',
      mockStep,
      [mockCode]
    );

    expect(session.sideSessionId).toContain('side-');
    expect(session.mainSessionId).toBe('main-sess-3344');
    expect(session.status).toBe('idle');
    expect(session.messages).toHaveLength(1);
    expect(session.messages[0].sender).toBe('system');
    expect(session.messages[0].content).toContain('零上下文污染');
  });

  it('generates tailored explainer answer for concurrency and complexity questions', () => {
    const snapshot = generateForkedSnapshot(
      'main-sess-5566',
      '高并发流式处理',
      mockStep
    );

    const answerConcurrency = generateLocalExplainerAnswer(
      '这段代码并发安全性如何？',
      snapshot
    );
    expect(answerConcurrency).toContain('并发场景');
    expect(answerConcurrency).toContain('无锁后台并发执行');

    const answerComplexity = generateLocalExplainerAnswer(
      '分析一下该算法的时间复杂度',
      snapshot
    );
    expect(answerComplexity).toContain('复杂度');
    expect(answerComplexity).toContain('O(1)');

    const answerGeneral = generateLocalExplainerAnswer(
      '为什么采用这种分层设计？',
      snapshot
    );
    expect(answerGeneral).toContain('单一职责');
  });
});
