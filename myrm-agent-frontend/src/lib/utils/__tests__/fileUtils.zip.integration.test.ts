/** @vitest-environment node */
import { describe, expect, it } from 'vitest';

import { buildZipFromFiles } from '../fileUtils';

describe('buildZipFromFiles real jszip integration', () => {
  it('keeps nested directory paths inside the produced zip', async () => {
    const files = {
      'plugin.json': '{"name":"myrm-memory"}',
      'mcp.json': '{"mcpServers":{}}',
      'skills/myrm-memory/SKILL.md': '# Persistent long-term memory',
    };

    const blob = await buildZipFromFiles(files);

    const { default: JSZip } = await import('jszip');
    const zip = await JSZip.loadAsync(await blob.arrayBuffer());
    const names = Object.keys(zip.files);
    expect(names).toContain('plugin.json');
    expect(names).toContain('mcp.json');
    expect(names).toContain('skills/myrm-memory/SKILL.md');
    expect(await zip.file('skills/myrm-memory/SKILL.md')?.async('string')).toContain('# Persistent long-term memory');
  });
});
