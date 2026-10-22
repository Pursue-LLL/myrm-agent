import { describe, it, expect } from 'vitest';
import {
  appendBoundedStderr,
  sanitizeStderrSnippet,
  classifyStderr,
  MAX_STDERR_BUFFER_BYTES,
} from '../stderrClassifier';

describe('stderrClassifier', () => {
  describe('appendBoundedStderr', () => {
    it('appends chunks within the 2 KiB limit', () => {
      const result = appendBoundedStderr('chunk1\n', 'chunk2\n');
      expect(result).toBe('chunk1\nchunk2\n');
    });

    it('truncates to keep only the latest 2 KiB tail when overflowing', () => {
      const hugeString = 'a'.repeat(3000);
      const result = appendBoundedStderr('', hugeString);
      expect(result.length).toBe(MAX_STDERR_BUFFER_BYTES);
    });
  });

  describe('sanitizeStderrSnippet', () => {
    it('redacts unix and windows user paths', () => {
      const raw = 'Traceback at /Users/developer/projects/open-perplexity/app.py in line 12';
      const sanitized = sanitizeStderrSnippet(raw);
      expect(sanitized).toBe('Traceback at [REDACTED_USER_PATH]/projects/open-perplexity/app.py in line 12');
    });

    it('redacts API keys and bearer tokens', () => {
      const raw = 'Error: Authorization failed with sk-123456789012345678901234 and Bearer eyJhbGciOiJIUzI1NiJ9';
      const sanitized = sanitizeStderrSnippet(raw);
      expect(sanitized).toContain('[REDACTED_API_KEY]');
      expect(sanitized).toContain('Bearer [REDACTED_TOKEN]');
    });
  });

  describe('classifyStderr', () => {
    it('classifies OOM killed process from exit code 137', () => {
      const res = classifyStderr('Killed', 137);
      expect(res.category).toBe('oom_killed');
      expect(res.categoryLabel).toContain('OOM');
      expect(res.fixGuides[0].actionType).toBe('increase_memory');
    });

    it('classifies missing python module', () => {
      const raw = "ModuleNotFoundError: No module named 'scipy'";
      const res = classifyStderr(raw, 1);
      expect(res.category).toBe('missing_dependency');
      expect(res.categoryLabel).toBe('缺少运行依赖: scipy');
      expect(res.fixGuides[0].buttonLabel).toBe('一键在沙箱安装 scipy');
      expect(res.fixGuides[0].payload?.package).toBe('scipy');
    });

    it('classifies missing node module', () => {
      const raw = "Error: Cannot find module 'lodash'";
      const res = classifyStderr(raw, 1);
      expect(res.category).toBe('missing_dependency');
      expect(res.categoryLabel).toBe('缺少运行依赖: lodash');
    });

    it('classifies port conflict EADDRINUSE', () => {
      const raw = 'Error: listen EADDRINUSE: address already in use :::8080';
      const res = classifyStderr(raw, 1);
      expect(res.category).toBe('port_conflict');
      expect(res.categoryLabel).toContain('8080');
      expect(res.fixGuides[0].actionType).toBe('change_port');
    });

    it('classifies auth invalid 401', () => {
      const raw = 'Request failed with status code 401 Unauthorized: Invalid API Key';
      const res = classifyStderr(raw, 1);
      expect(res.category).toBe('auth_invalid');
      expect(res.fixGuides[0].actionType).toBe('open_settings');
    });

    it('classifies network timeout', () => {
      const raw = 'connect ETIMEDOUT 142.250.190.46:443';
      const res = classifyStderr(raw, 1);
      expect(res.category).toBe('network_timeout');
    });

    it('falls back to unknown failure', () => {
      const raw = 'Unrecognized process error occurred';
      const res = classifyStderr(raw, 42);
      expect(res.category).toBe('unknown_failure');
      expect(res.exitCode).toBe(42);
    });
  });
});
