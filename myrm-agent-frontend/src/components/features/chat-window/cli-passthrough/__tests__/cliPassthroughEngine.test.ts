import { describe, it, expect } from 'vitest';
import {
  parseCliPassThroughInput,
  auditCliCommand,
  formatCliOutputForContext,
} from '../cliPassthroughEngine';

describe('cliPassthroughEngine', () => {
  describe('parseCliPassThroughInput', () => {
    it('returns false for empty or regular messages', () => {
      expect(parseCliPassThroughInput('')).toEqual({ isCliCommand: false });
      expect(parseCliPassThroughInput('   ')).toEqual({ isCliCommand: false });
      expect(parseCliPassThroughInput('这是一条普通的对话消息')).toEqual({ isCliCommand: false });
      expect(parseCliPassThroughInput('!   ')).toEqual({ isCliCommand: false });
      expect(parseCliPassThroughInput('!!   ')).toEqual({ isCliCommand: false });
    });

    it('parses single exclamation mark as visible_to_context mode', () => {
      const result = parseCliPassThroughInput('! npm test');
      expect(result.isCliCommand).toBe(true);
      expect(result.mode).toBe('visible_to_context');
      expect(result.command).toBe('npm test');

      const resultWithExtraSpaces = parseCliPassThroughInput('!   pytest -q  ');
      expect(resultWithExtraSpaces.isCliCommand).toBe(true);
      expect(resultWithExtraSpaces.mode).toBe('visible_to_context');
      expect(resultWithExtraSpaces.command).toBe('pytest -q');
    });

    it('parses double exclamation mark as user_inspection_only mode', () => {
      const result = parseCliPassThroughInput('!! git status');
      expect(result.isCliCommand).toBe(true);
      expect(result.mode).toBe('user_inspection_only');
      expect(result.command).toBe('git status');

      const resultWithPipes = parseCliPassThroughInput('!! ps aux | grep node');
      expect(resultWithPipes.isCliCommand).toBe(true);
      expect(resultWithPipes.mode).toBe('user_inspection_only');
      expect(resultWithPipes.command).toBe('ps aux | grep node');
    });
  });

  describe('auditCliCommand', () => {
    it('allows benign developer commands', () => {
      expect(auditCliCommand('npm run build').allowed).toBe(true);
      expect(auditCliCommand('git status').allowed).toBe(true);
      expect(auditCliCommand('ls -la').allowed).toBe(true);
      expect(auditCliCommand('cargo check').allowed).toBe(true);
      expect(auditCliCommand('python3 main.py').allowed).toBe(true);
    });

    it('rejects empty commands', () => {
      const res = auditCliCommand('   ');
      expect(res.allowed).toBe(false);
      expect(res.reason).toBe('命令内容不能为空');
    });

    it('blocks high-risk destruction patterns', () => {
      const rmRoot = auditCliCommand('rm -rf /');
      expect(rmRoot.allowed).toBe(false);
      expect(rmRoot.reason).toContain('高危操作拦截');

      const rmHome = auditCliCommand('rm -rf ~');
      expect(rmHome.allowed).toBe(false);

      const mkfs = auditCliCommand('mkfs.ext4 /dev/nvme0n1');
      expect(mkfs.allowed).toBe(false);

      const forkBomb = auditCliCommand(':(){ :|:& };:');
      expect(forkBomb.allowed).toBe(false);

      const ddZero = auditCliCommand('dd if=/dev/zero of=/dev/sda bs=1M');
      expect(ddZero.allowed).toBe(false);

      const chmodGlobal = auditCliCommand('chmod -R 777 /');
      expect(chmodGlobal.allowed).toBe(false);
    });
  });

  describe('formatCliOutputForContext', () => {
    it('formats successful execution output with metadata', () => {
      const formatted = formatCliOutputForContext('npm test', 'PASS src/index.test.ts', 0);
      expect(formatted).toContain('[USER_CMD_EXEC]');
      expect(formatted).toContain('$ npm test');
      expect(formatted).toContain('STATUS: SUCCESS');
      expect(formatted).toContain('PASS src/index.test.ts');
      expect(formatted).toContain('[/USER_CMD_EXEC]');
    });

    it('formats failed execution output with exit code', () => {
      const formatted = formatCliOutputForContext('cargo test', 'test failed on thread main', 101);
      expect(formatted).toContain('STATUS: FAILED (Exit Code: 101)');
      expect(formatted).toContain('test failed on thread main');
    });
  });
});
