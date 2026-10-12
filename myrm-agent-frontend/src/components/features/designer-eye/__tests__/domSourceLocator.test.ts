/**
 * [INPUT]
 * - domSourceLocator utility from ../domSourceLocator
 *
 * [OUTPUT]
 * - Comprehensive unit tests for normalizeSourceFilePath, buildConciseCssSelector,
 *   resolveFiberSource, extractComponentHierarchy, inferCandidateSourceFiles, and extractInspectionFingerprint
 *
 * [POS]
 * Unit test suite for DOM-to-Component AST & Fiber reverse locator in Designer's Eye.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  normalizeSourceFilePath,
  buildConciseCssSelector,
  resolveFiberSource,
  extractComponentHierarchy,
  inferCandidateSourceFiles,
  extractInspectionFingerprint,
} from '../domSourceLocator';

describe('domSourceLocator', () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.body.removeChild(container);
  });

  describe('normalizeSourceFilePath', () => {
    it('normalizes webpack query parameters and windows backslashes', () => {
      const input = 'C:\\Projects\\myrm-agent-frontend\\src\\components\\Button.tsx?t=12345';
      const output = normalizeSourceFilePath(input);
      expect(output).toBe('src/components/Button.tsx');
    });

    it('extracts path starting from src/ directory', () => {
      const input = '/Users/dev/repos/myrm/src/components/features/chat/ChatBox.tsx';
      expect(normalizeSourceFilePath(input)).toBe('src/components/features/chat/ChatBox.tsx');
    });

    it('handles paths that already start with src/', () => {
      const input = 'src/components/common/Card.tsx';
      expect(normalizeSourceFilePath(input)).toBe('src/components/common/Card.tsx');
    });
  });

  describe('buildConciseCssSelector', () => {
    it('uses element id if present', () => {
      const btn = document.createElement('button');
      btn.id = 'send-message-btn';
      btn.className = 'px-4 py-2 bg-blue-500';
      container.appendChild(btn);

      const selector = buildConciseCssSelector(btn);
      expect(selector).toBe('button#send-message-btn');
    });

    it('uses top classes when id is absent', () => {
      const card = document.createElement('div');
      card.className = 'glass-card rounded-xl shadow-md hover:opacity-80';
      container.appendChild(card);

      const selector = buildConciseCssSelector(card);
      expect(selector).toBe('div.glass-card.rounded-xl.shadow-md');
    });

    it('falls back to structural selector when classes are absent', () => {
      const parent = document.createElement('section');
      const p1 = document.createElement('p');
      const p2 = document.createElement('p');
      parent.appendChild(p1);
      parent.appendChild(p2);
      container.appendChild(parent);

      const selector = buildConciseCssSelector(p2);
      expect(selector).toBe('section > p:nth-of-type(2)');
    });
  });

  describe('React Fiber source resolution', () => {
    it('resolves Fiber _debugSource when present on element', () => {
      const button = document.createElement('button');
      container.appendChild(button);

      // Attach mock Fiber instance with debugSource
      const mockFiber = {
        type: { displayName: 'SendButton' },
        _debugSource: {
          fileName: '/home/project/myrm-agent-frontend/src/components/features/chat/SendButton.tsx',
          lineNumber: 42,
          columnNumber: 5,
        },
      };

      (button as unknown as Record<string, unknown>)['__reactFiber$abc123'] = mockFiber;

      const result = resolveFiberSource(button);
      expect(result).not.toBeNull();
      expect(result?.componentName).toBe('SendButton');
      expect(result?.fileName).toBe('src/components/features/chat/SendButton.tsx');
      expect(result?.lineNumber).toBe(42);
      expect(result?.columnNumber).toBe(5);
      expect(result?.confidence).toBe('fiber_debug');
    });

    it('walks up Fiber return chain to find debugSource on ancestor', () => {
      const span = document.createElement('span');
      container.appendChild(span);

      // Inner span fiber has no debugSource, ancestor Card component has one
      const parentFiber = {
        type: { name: 'MetricCard' },
        _debugSource: {
          fileName: 'src/components/features/stats/MetricCard.tsx',
          lineNumber: 88,
        },
      };

      const innerFiber = {
        type: 'span',
        return: parentFiber,
      };

      (span as unknown as Record<string, unknown>)['__reactFiber$child'] = innerFiber;

      const result = resolveFiberSource(span);
      expect(result?.componentName).toBe('MetricCard');
      expect(result?.fileName).toBe('src/components/features/stats/MetricCard.tsx');
      expect(result?.lineNumber).toBe(88);
    });

    it('extracts complete component hierarchy names', () => {
      const input = document.createElement('input');
      container.appendChild(input);

      const rootFiber = {
        type: { displayName: 'AppShell' },
      };
      const midFiber = {
        type: { displayName: 'SearchBar' },
        return: rootFiber,
      };
      const inputFiber = {
        type: 'input',
        return: midFiber,
      };

      (input as unknown as Record<string, unknown>)['__reactFiber$input'] = inputFiber;

      const hierarchy = extractComponentHierarchy(input);
      expect(hierarchy).toEqual(['SearchBar', 'AppShell']);
    });
  });

  describe('inferCandidateSourceFiles', () => {
    it('infers file candidates from component hierarchy and hint', () => {
      const candidates = inferCandidateSourceFiles(['MobileHeader', 'MobileView'], 'MobileHeader');
      expect(candidates.length).toBeGreaterThan(0);
      expect(candidates[0].componentName).toBe('MobileHeader');
      expect(candidates[0].confidence).toBe('hierarchy_match');
      expect(candidates.some((c) => c.fileName.includes('MobileHeader.tsx'))).toBe(true);
    });
  });

  describe('extractInspectionFingerprint', () => {
    it('creates complete fingerprint snapshot of an element', () => {
      const div = document.createElement('div');
      div.id = 'status-hub';
      div.className = 'flex items-center p-4';
      div.innerText = 'Service Status: Online';
      div.setAttribute('data-component', 'ServiceStatusBanner');
      container.appendChild(div);

      const fp = extractInspectionFingerprint(div);
      expect(fp.tagName).toBe('div');
      expect(fp.id).toBe('status-hub');
      expect(fp.selector).toBe('div#status-hub');
      expect(fp.textContentSnippet).toBe('Service Status: Online');
      expect(fp.candidates.length).toBeGreaterThan(0);
      expect(fp.candidates[0].componentName).toBe('ServiceStatusBanner');
    });
  });
});
