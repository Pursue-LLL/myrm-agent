import { describe, it, expect } from 'vitest';
import { isValidElement } from 'react';

import { getSemanticToolLabel, linkifyErrorText } from '../utils';

type AnchorElement = React.ReactElement<React.AnchorHTMLAttributes<HTMLAnchorElement>>;

describe('linkifyErrorText', () => {
  it('converts a URL into a React anchor element', () => {
    const nodes = linkifyErrorText('Check https://platform.openai.com/api-keys now');
    expect(nodes).toHaveLength(3);
    expect(nodes[0]).toBe('Check ');
    expect(isValidElement(nodes[1])).toBe(true);
    const anchor = nodes[1] as AnchorElement;
    expect(anchor.props.href).toBe('https://platform.openai.com/api-keys');
    expect(anchor.props.target).toBe('_blank');
    expect(anchor.props.rel).toBe('noopener noreferrer');
    expect(nodes[2]).toBe(' now');
  });

  it('handles multiple URLs', () => {
    const nodes = linkifyErrorText('Go to https://a.com and http://b.com please');
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(2);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://a.com');
    expect((anchors[1] as AnchorElement).props.href).toBe('http://b.com');
  });

  it('returns plain text when no URLs present', () => {
    const nodes = linkifyErrorText('No URL here');
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toBe('No URL here');
    expect(nodes.filter(isValidElement)).toHaveLength(0);
  });

  it('handles URLs with query params and hash', () => {
    const nodes = linkifyErrorText('Visit http://x.com/path?q=1#sec');
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('http://x.com/path?q=1#sec');
  });

  it('stops URL at closing parenthesis', () => {
    const nodes = linkifyErrorText('(https://example.com) details');
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://example.com');
  });

  it('handles multi-line text', () => {
    const text = '1. Check key\n2. Visit https://openai.com\n3. Retry';
    const nodes = linkifyErrorText(text);
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://openai.com');
  });

  it('does NOT render HTML tags from malicious error text (XSS prevention)', () => {
    const malicious = 'Error <script>alert(1)</script> see https://safe.com';
    const nodes = linkifyErrorText(malicious);
    const strings = nodes.filter((n): n is string => typeof n === 'string');
    const joined = strings.join('');
    expect(joined).toContain('<script>alert(1)</script>');
    expect(nodes.filter(isValidElement)).toHaveLength(1);
  });

  it('returns empty string segment for URL-only text', () => {
    const nodes = linkifyErrorText('https://only-url.com');
    expect(nodes).toHaveLength(3);
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://only-url.com');
  });
});

describe('getSemanticToolLabel', () => {
  const mockT = (key: string) => key;

  it('returns i18n translation when available', () => {
    const t = (key: string) => (key === 'toolSemanticLabels.file_read_tool' ? 'Read File' : key);
    expect(getSemanticToolLabel('file_read_tool', t)).toBe('Read File');
  });

  it('formats regular tool name when no translation', () => {
    expect(getSemanticToolLabel('file_read_tool', mockT)).toBe('File Read');
  });

  it('extracts tool part from MCP prefixed name', () => {
    expect(getSemanticToolLabel('mcp__github__search_repos', mockT)).toBe('Search Repos');
  });

  it('handles MCP tool with single-word tool name', () => {
    expect(getSemanticToolLabel('mcp__filesystem__read', mockT)).toBe('Read');
  });

  it('strips _tool suffix from MCP tool name', () => {
    expect(getSemanticToolLabel('mcp__remote__file_read_tool', mockT)).toBe('File Read');
  });

  it('handles MCP name with double underscore in tool part', () => {
    expect(getSemanticToolLabel('mcp__server__complex__action', mockT)).toBe('Complex Action');
  });

  it('handles MCP prefix with only server (no tool delimiter)', () => {
    expect(getSemanticToolLabel('mcp__serveronly', mockT)).toBe('Serveronly');
  });

  it('formats plain tool name without _tool suffix', () => {
    expect(getSemanticToolLabel('web_search', mockT)).toBe('Web Search');
  });

  it('capitalizes each word', () => {
    expect(getSemanticToolLabel('bash_code_execute_tool', mockT)).toBe('Bash Code Execute');
  });

  it('handles empty string', () => {
    expect(getSemanticToolLabel('', mockT)).toBe('');
  });

  it('handles single character tool name', () => {
    expect(getSemanticToolLabel('a', mockT)).toBe('A');
  });

  it('handles MCP prefix with empty tool part', () => {
    expect(getSemanticToolLabel('mcp__server__', mockT)).toBe('');
  });

  it('does not treat non-mcp double underscore as MCP prefix', () => {
    expect(getSemanticToolLabel('some__internal__name', mockT)).toBe('Some  Internal  Name');
  });

  it('preserves i18n for MCP tool when translation exists', () => {
    const t = (key: string) => (key === 'toolSemanticLabels.mcp__github__search_repos' ? 'Search GitHub Repos' : key);
    expect(getSemanticToolLabel('mcp__github__search_repos', t)).toBe('Search GitHub Repos');
  });
});
