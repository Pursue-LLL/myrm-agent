import { describe, it, expect } from 'vitest';
import {
  resolveLaneGradientSpec,
  detectGraduationIntent,
  formatLaneDisplay,
  buildGraduationEvent,
} from '../laneSemanticEngine';

describe('laneSemanticEngine', () => {
  describe('resolveLaneGradientSpec', () => {
    it('resolves cloud sandbox when sandboxMode is true', () => {
      const spec = resolveLaneGradientSpec('agent', true, null);
      expect(spec.laneType).toBe('workspace');
      expect(spec.envMode).toBe('cloud_sandbox');
      expect(spec.canWriteFiles).toBe(true);
      expect(spec.canExecCommands).toBe(true);
      expect(spec.badgeColor).toBe('indigo');
      expect(spec.capabilities).toContain('code_sandbox');
    });

    it('resolves local workspace when workspaceDir is present or actionMode is agent', () => {
      const specWithDir = resolveLaneGradientSpec('fast', false, '/my/workspace');
      expect(specWithDir.laneType).toBe('workspace');
      expect(specWithDir.envMode).toBe('local_workspace');
      expect(specWithDir.canWriteFiles).toBe(true);
      expect(specWithDir.badgeColor).toBe('emerald');

      const specWithAgent = resolveLaneGradientSpec('agent', false, null);
      expect(specWithAgent.laneType).toBe('workspace');
      expect(specWithAgent.envMode).toBe('local_workspace');
    });

    it('resolves fast chat lane by default', () => {
      const spec = resolveLaneGradientSpec('fast', false, null);
      expect(spec.laneType).toBe('chat');
      expect(spec.envMode).toBe('fast_chat');
      expect(spec.canWriteFiles).toBe(false);
      expect(spec.canExecCommands).toBe(false);
      expect(spec.badgeColor).toBe('sky');
    });
  });

  describe('detectGraduationIntent', () => {
    it('returns null if already in workspace lane', () => {
      const result = detectGraduationIntent('请帮我修改 src/App.tsx 并执行 npm test', 'workspace');
      expect(result).toBeNull();
    });

    it('returns null for empty or conversational text', () => {
      expect(detectGraduationIntent('', 'chat')).toBeNull();
      expect(detectGraduationIntent('   ', 'chat')).toBeNull();
      expect(detectGraduationIntent('什么是 React 中的 Hook？', 'chat')).toBeNull();
      expect(detectGraduationIntent('你好，请帮我分析一下这段文本的语法。', 'chat')).toBeNull();
    });

    it('detects file write intent', () => {
      const result = detectGraduationIntent('请把生成的文件保存到 src/components/Card.tsx', 'chat');
      expect(result).not.toBeNull();
      expect(result?.triggerKind).toBe('file_write');
      expect(result?.confidence).toBeGreaterThan(0.9);
      expect(result?.suggestedTargetMode).toBe('local_workspace');
    });

    it('detects shell command execution intent', () => {
      const result = detectGraduationIntent('请在终端运行 npm test 测试一下', 'chat');
      expect(result).not.toBeNull();
      expect(result?.triggerKind).toBe('shell_command');
      expect(result?.matchedKeyword).toMatch(/终端运行|npm\s+test/i);
    });

    it('detects project scaffold intent', () => {
      const result = detectGraduationIntent('请帮我初始化项目骨架，搭建项目目录结构', 'chat');
      expect(result).not.toBeNull();
      expect(result?.triggerKind).toBe('project_scaffold');
    });

    it('detects dependency install intent', () => {
      const result = detectGraduationIntent('需要安装依赖 lodash 和 axios', 'chat');
      expect(result).not.toBeNull();
      expect(result?.triggerKind).toBe('dependency_install');
      expect(result?.suggestedTargetMode).toBe('cloud_sandbox');
    });

    it('detects git operation intent', () => {
      const result = detectGraduationIntent('请帮我创建分支并提交代码', 'chat');
      expect(result).not.toBeNull();
      expect(result?.triggerKind).toBe('git_operation');
    });
  });

  describe('formatLaneDisplay', () => {
    it('formats default display strings properly', () => {
      const spec = resolveLaneGradientSpec('fast', false, null);
      const display = formatLaneDisplay(spec);
      expect(display.title).toBe('快速对话通道');
      expect(display.badgeText).toBe('对话通道');
      expect(display.description).toContain('纯文本会话');
    });
  });

  describe('buildGraduationEvent', () => {
    it('constructs a valid LaneGraduationEvent', () => {
      const fromSpec = resolveLaneGradientSpec('fast', false, null);
      const event = buildGraduationEvent({
        fromSpec,
        toEnvMode: 'local_workspace',
        reason: '检测到文件写入意图',
        workspaceDir: '/home/user/app',
      });

      expect(event.fromLane).toBe('chat');
      expect(event.toLane).toBe('workspace');
      expect(event.toEnvMode).toBe('local_workspace');
      expect(event.workspaceDir).toBe('/home/user/app');
      expect(event.id).toMatch(/^grad_\d+_/);
    });
  });
});
