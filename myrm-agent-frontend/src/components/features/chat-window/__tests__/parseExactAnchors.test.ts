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

  it('tolerates variable header levels like ## ⚓ Exact Anchor Index', () => {
    const md = `## ⚓ Exact Anchor Index (Deterministic Machine Symbols)
- **Git Commits**: \`abc1234\`
- **Modified Files**: \`test.ts\`

# Final Section`;
    const res = parseExactAnchors(md);
    expect(res.anchors.commitShas).toEqual(['abc1234']);
    expect(res.anchors.filePaths).toEqual(['test.ts']);
    expect(res.cleanedSummary).toBe('# Final Section');
  });

  it('parses dual-mode backend gold standard output with JSON comment and markdown table', () => {
    const backendGoldStandard = `# Context Compaction

### ⚓ Exact Anchor Index (Machine-Extracted Truth)
<!-- Immutable historical anchors; do not hallucinate alternatives -->
- **Git Commits**: \`7f8a91c\`
- **Modified Files**: \`docker-compose.prod.yml\`, \`nginx.conf\`
- **Key Symbols**: \`ConfigParser\`
- **API Endpoints**: \`/api/v1/health\`
- **Error Signatures**:
  * \`FATAL ERROR: heap out of memory\`
<!-- EXACT_ANCHOR_JSON: {"commit_shas":["7f8a91c"],"file_paths":["docker-compose.prod.yml","nginx.conf"],"error_spans":["FATAL ERROR: heap out of memory"],"code_symbols":["ConfigParser"],"api_endpoints":["/api/v1/health"]} -->

## Active Task
Continue deployment.`;

    const res = parseExactAnchors(backendGoldStandard);
    expect(res.anchors.commitShas).toEqual(['7f8a91c']);
    expect(res.anchors.filePaths).toEqual(['docker-compose.prod.yml', 'nginx.conf']);
    expect(res.anchors.codeSymbols).toEqual(['ConfigParser']);
    expect(res.anchors.apiEndpoints).toEqual(['/api/v1/health']);
    expect(res.anchors.errorSpans).toEqual(['FATAL ERROR: heap out of memory']);
    expect(res.cleanedSummary).toContain('# Context Compaction');
    expect(res.cleanedSummary).toContain('## Active Task');
    expect(res.cleanedSummary).not.toContain('⚓ Exact Anchor Index');
    expect(res.cleanedSummary).not.toContain('EXACT_ANCHOR_JSON');
  });

  it('tolerates legacy [Verified Exact Anchors] format gracefully', () => {
    const legacyMd = `[Verified Exact Anchors - Machine-Extracted Truth]
- **Git Commits**: \`c0ffee1\`
- **Modified Files**: \`legacy.py\`

## Summary
Done.`;
    const res = parseExactAnchors(legacyMd);
    expect(res.anchors.commitShas).toEqual(['c0ffee1']);
    expect(res.anchors.filePaths).toEqual(['legacy.py']);
    expect(res.cleanedSummary).toContain('## Summary');
    expect(res.cleanedSummary).not.toContain('Verified Exact Anchors');
  });
});
