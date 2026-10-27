import { describe, expect, it } from 'vitest';
import { stripYamlFrontmatter } from '../frontmatter';

describe('stripYamlFrontmatter', () => {
  it('removes a leading block of YAML keys and keeps the body as it is', () => {
    const withMeta = '---\nsource_chat: chat-abc\nsource_message: msg-xyz\n---\n# title\n\nbody';
    expect(stripYamlFrontmatter(withMeta)).toBe('# title\n\nbody');
  });

  it('copes with Windows line breaks, spaces after the markers and a byte order mark', () => {
    expect(stripYamlFrontmatter('---\r\nname: demo\r\n---\r\n# title')).toBe('# title');
    expect(stripYamlFrontmatter('--- \nname: demo\n---\t\n# title')).toBe('# title');
    expect(stripYamlFrontmatter('\uFEFF---\nname: demo\n---\n# title')).toBe('# title');
  });

  it('leaves nothing for a file that holds only front matter, with or without a final line break', () => {
    expect(stripYamlFrontmatter('---\nname: demo\n---\n')).toBe('');
    expect(stripYamlFrontmatter('---\nname: demo\n---')).toBe('');
  });

  it('removes only the first block, so a rule in the body survives', () => {
    expect(stripYamlFrontmatter('---\nname: demo\n---\n# title\n\n---\nlater')).toBe('# title\n\n---\nlater');
  });

  it('keeps a key whose value is empty or comes on the next lines', () => {
    expect(stripYamlFrontmatter('---\ntags:\n  - a\n  - b\n---\nbody')).toBe('body');
  });

  it('does not touch text that does not start with a front matter block', () => {
    expect(stripYamlFrontmatter('# plain markdown')).toBe('# plain markdown');
    expect(stripYamlFrontmatter('\n---\nname: demo\n---\nbody')).toBe('\n---\nname: demo\n---\nbody');
    expect(stripYamlFrontmatter('---\nname: demo\nno closing marker')).toBe('---\nname: demo\nno closing marker');
    expect(stripYamlFrontmatter('')).toBe('');
  });

  it('does not take a document that opens with a rule for front matter, which would hide the text between the rules', () => {
    const rules = '---\n# Title\nSome text\n---\nmore';
    expect(stripYamlFrontmatter(rules)).toBe(rules);
    const prose = '---\nJust a sentence without a key\n---\nbody';
    expect(stripYamlFrontmatter(prose)).toBe(prose);
    const empty = '---\n---\nbody\n\n---\nlater';
    expect(stripYamlFrontmatter(empty)).toBe(empty);
  });

  it('does not accept a longer line of dashes as the closing marker', () => {
    const longer = '---\nname: demo\n----\nbody';
    expect(stripYamlFrontmatter(longer)).toBe(longer);
  });
});
