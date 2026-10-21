import { describe, it, expect } from 'vitest';
import { getLineTone } from '../lineToneUtils';

describe('getLineTone', () => {
  describe('command tone', () => {
    it('matches $ prompt', () => {
      expect(getLineTone('$ npm install')).toBe('command');
    });

    it('matches ❯ prompt', () => {
      expect(getLineTone('❯ bun run dev')).toBe('command');
    });

    it('matches ► prompt', () => {
      expect(getLineTone('► git status')).toBe('command');
    });

    it('matches indented $ prompt', () => {
      expect(getLineTone('  $ ls -la')).toBe('command');
    });
  });

  describe('error tone', () => {
    it('matches Error keyword', () => {
      expect(getLineTone('Error: ENOENT: no such file')).toBe('error');
    });

    it('matches FAIL keyword', () => {
      expect(getLineTone('FAIL src/test.ts')).toBe('error');
    });

    it('matches failed keyword', () => {
      expect(getLineTone('npm ERR! command failed')).toBe('error');
    });

    it('matches traceback keyword', () => {
      expect(getLineTone('Traceback (most recent call last):')).toBe('error');
    });

    it('matches ✖ symbol', () => {
      expect(getLineTone('✖ Build failed')).toBe('error');
    });

    it('matches panic keyword', () => {
      expect(getLineTone('panic: runtime error')).toBe('error');
    });
  });

  describe('warning tone', () => {
    it('matches warning keyword', () => {
      expect(getLineTone('warning: deprecated package @types/x')).toBe('warning');
    });

    it('matches DEPRECATED', () => {
      expect(getLineTone('npm WARN deprecated glob@7.1.0')).toBe('warning');
    });

    it('matches caution', () => {
      expect(getLineTone('caution: this may break')).toBe('warning');
    });
  });

  describe('success tone', () => {
    it('matches ✔ symbol', () => {
      expect(getLineTone('✔ All tests passed')).toBe('success');
    });

    it('matches PASS keyword', () => {
      expect(getLineTone('PASS src/utils.test.ts')).toBe('success');
    });

    it('matches done keyword', () => {
      expect(getLineTone('Done in 3.2s')).toBe('success');
    });

    it('matches success keyword', () => {
      expect(getLineTone('Build success')).toBe('success');
    });

    it('matches completed keyword', () => {
      expect(getLineTone('Installation completed')).toBe('success');
    });

    it('matches ok with word boundary', () => {
      expect(getLineTone('HTTP/1.1 200 ok')).toBe('success');
    });
  });

  describe('muted tone', () => {
    it('matches box-drawing characters', () => {
      expect(getLineTone('╭──────────────╮')).toBe('muted');
    });

    it('matches timestamp-like patterns', () => {
      expect(getLineTone('2026-05-26 10:30:00')).toBe('muted');
    });
  });

  describe('default tone', () => {
    it('returns default for empty lines', () => {
      expect(getLineTone('')).toBe('default');
      expect(getLineTone('   ')).toBe('default');
    });

    it('returns default for ordinary output', () => {
      expect(getLineTone('added 142 packages')).toBe('default');
    });

    it('returns default for file paths', () => {
      expect(getLineTone('  src/components/Button.tsx')).toBe('default');
    });

    it('does not mis-match markdown blockquote as command', () => {
      expect(getLineTone('> This is a quote')).toBe('default');
    });
  });

  describe('priority ordering', () => {
    it('command takes priority over error (e.g. "$ error test")', () => {
      expect(getLineTone('$ run error-handler')).toBe('command');
    });

    it('error takes priority over success (line with both)', () => {
      expect(getLineTone('error: build failed but done')).toBe('error');
    });
  });
});
