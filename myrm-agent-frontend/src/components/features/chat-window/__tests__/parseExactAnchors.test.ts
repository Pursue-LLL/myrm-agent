import { describe, it, expect } from 'vitest';
import { parseExactAnchors } from '../parseExactAnchors';

describe('parseExactAnchors', () => {
  it('returns empty anchors for empty text', () => {
    const res = parseExactAnchors('');
    expect(res.anchors.commitShas).toEqual([]);
    expect(res.anchors.filePaths).toEqual([]);
    expect(res.cleanedSummary).toBe('');
  });

  it('prioritizes valid metaAnchors when passed', () => {
    const meta = {
      commitShas: ['abcd123'],
      filePaths: ['src/main.ts'],
      errorSpans: [],
      codeSymbols: [],
      apiEndpoints: [],
    };
    const res = parseExactAnchors('# Summary Title', meta);
    expect(res.anchors.commitShas).toEqual(['abcd123']);
    expect(res.anchors.filePaths).toEqual(['src/main.ts']);
    expect(res.cleanedSummary).toBe('# Summary Title');
  });

  it('parses markdown anchor index block and strips it from summary', () => {
    const md = `# Turn Summary

### ⚓ Exact Anchor Index (Deterministic Machine Symbols)
- **Git Commits**: \`7f8a9b0\`, \`1234567\`
- **Modified Files**: \`src/agent/loop.py\`, \`frontend/app.tsx\`
- **Key Symbols**: \`ContextManager\`, \`run_loop\`
- **API Endpoints**: \`POST /api/v1/chat\`
- **Resolved Errors**:
  * \`ValueError: invalid token at line 42\`

## Next Steps
Proceed with tests.`;

    const res = parseExactAnchors(md);
    expect(res.anchors.commitShas).toEqual(['7f8a9b0', '1234567']);
    expect(res.anchors.filePaths).toEqual(['src/agent/loop.py', 'frontend/app.tsx']);
    expect(res.anchors.codeSymbols).toEqual(['ContextManager', 'run_loop']);
    expect(res.anchors.apiEndpoints).toEqual(['POST /api/v1/chat']);
    expect(res.anchors.errorSpans).toEqual(['ValueError: invalid token at line 42']);

    // Ensure anchor block was removed from cleanedSummary
    expect(res.cleanedSummary).toContain('# Turn Summary');
    expect(res.cleanedSummary).toContain('## Next Steps');
    expect(res.cleanedSummary).not.toContain('### ⚓ Exact Anchor Index');
  });

  it('parses JSON metadata comment when present', () => {
    const jsonBlock = `<!-- EXACT_ANCHOR_JSON: {"commit_shas": ["1a2b3c4"], "file_paths": ["foo.py"], "code_symbols": ["Bar"]} -->\n# Markdown Summary`;
    const res = parseExactAnchors(jsonBlock);
    expect(res.anchors.commitShas).toEqual(['1a2b3c4']);
    expect(res.anchors.filePaths).toEqual(['foo.py']);
    expect(res.anchors.codeSymbols).toEqual(['Bar']);
    expect(res.cleanedSummary).toBe('# Markdown Summary');
  });
});
