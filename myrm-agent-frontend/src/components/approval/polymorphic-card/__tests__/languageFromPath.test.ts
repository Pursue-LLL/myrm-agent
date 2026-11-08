import { describe, expect, it } from 'vitest';
import { getLanguageFromPath } from '../languageFromPath';

describe('getLanguageFromPath', () => {
  it.each([
    ['src/app.js', 'javascript'],
    ['src/App.jsx', 'javascript'],
    ['src/app.ts', 'typescript'],
    ['src/App.tsx', 'typescript'],
    ['tool.py', 'python'],
    ['package.json', 'json'],
    ['index.html', 'html'],
    ['styles.css', 'css'],
    ['README.md', 'markdown'],
    ['run.sh', 'shell'],
    ['run.bash', 'shell'],
    ['ci.yaml', 'yaml'],
    ['ci.yml', 'yaml'],
    ['lib.rs', 'rust'],
    ['main.go', 'go'],
    ['Main.java', 'java'],
    ['main.cpp', 'cpp'],
    ['main.c', 'cpp'],
    ['main.h', 'cpp'],
    ['main.hpp', 'cpp'],
  ])('maps %s to %s', (path, language) => {
    expect(getLanguageFromPath(path)).toBe(language);
  });

  it('reads the extension case-insensitively and from the last dot', () => {
    expect(getLanguageFromPath('SCRIPT.PY')).toBe('python');
    expect(getLanguageFromPath('archive.tar.json')).toBe('json');
    expect(getLanguageFromPath('v1.2/notes.md')).toBe('markdown');
  });

  it('treats an unknown extension, or none, as plain text', () => {
    expect(getLanguageFromPath('data.xyz')).toBe('plaintext');
    expect(getLanguageFromPath('Makefile')).toBe('plaintext');
    expect(getLanguageFromPath('dir.d/file')).toBe('plaintext');
  });

  it('treats an empty path as markdown', () => {
    expect(getLanguageFromPath('')).toBe('markdown');
  });
});
