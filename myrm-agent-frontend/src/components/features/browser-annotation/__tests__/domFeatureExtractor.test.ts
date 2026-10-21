import { describe, it, expect, beforeEach } from 'vitest';
import {
  sanitizeElementTextAndHtml,
  generateCssSelector,
  extractComputedLayoutStyles,
  detectSubtreeBranch,
  partitionPinsBySubtree,
} from '../domFeatureExtractor';
import type { BrowserAnnotationPin } from '../browserAnnotationTypes';

describe('domFeatureExtractor', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  describe('sanitizeElementTextAndHtml', () => {
    it('masks password values in input elements', () => {
      const rawHtml = '<input type="password" name="pwd" value="superSecret123" />';
      const { sanitizedHtml } = sanitizeElementTextAndHtml(rawHtml, 'superSecret123');
      expect(sanitizedHtml).toContain('value="[REDACTED]"');
      expect(sanitizedHtml).not.toContain('superSecret123');
    });

    it('masks bearer tokens and api keys', () => {
      const rawHtml = '<div data-token="Bearer eyJhbGciOiJIUzI1NiJ9">Token Info</div>';
      const rawText = 'Authorization: Bearer sk-ant-secret123456789';
      const { sanitizedHtml, sanitizedText } = sanitizeElementTextAndHtml(rawHtml, rawText);
      expect(sanitizedHtml).toContain('[REDACTED]');
      expect(sanitizedText).toContain('[REDACTED]');
      expect(sanitizedText).not.toContain('secret123456789');
    });

    it('truncates overly long texts and html', () => {
      const longText = 'A'.repeat(300);
      const longHtml = `<p>${'B'.repeat(800)}</p>`;
      const { sanitizedHtml, sanitizedText } = sanitizeElementTextAndHtml(longHtml, longText);
      expect(sanitizedText.length).toBeLessThanOrEqual(165);
      expect(sanitizedText.endsWith('...')).toBe(true);
      expect(sanitizedHtml.length).toBeLessThanOrEqual(505);
      expect(sanitizedHtml.endsWith('...')).toBe(true);
    });
  });

  describe('generateCssSelector', () => {
    it('returns id selector directly when element has an id', () => {
      const el = document.createElement('button');
      el.id = 'submit-btn';
      document.body.appendChild(el);
      expect(generateCssSelector(el)).toBe('#submit-btn');
    });

    it('generates hierarchy selector with tags and classes', () => {
      const container = document.createElement('div');
      container.id = 'app-root';
      const section = document.createElement('section');
      section.className = 'content-area main-layout';
      const btn = document.createElement('button');
      btn.className = 'primary-btn';
      section.appendChild(btn);
      container.appendChild(section);
      document.body.appendChild(container);

      const selector = generateCssSelector(btn);
      expect(selector).toBe('#app-root > section.content-area.main-layout > button.primary-btn');
    });

    it('uses nth-of-type for sibling elements of the same tag', () => {
      const list = document.createElement('ul');
      const item1 = document.createElement('li');
      const item2 = document.createElement('li');
      list.appendChild(item1);
      list.appendChild(item2);
      document.body.appendChild(list);

      const selector = generateCssSelector(item2);
      expect(selector).toContain('li:nth-of-type(2)');
    });
  });

  describe('extractComputedLayoutStyles', () => {
    it('filters out non-essential and default styles', () => {
      const mockStyle = {
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        width: '320px',
        height: '240px',
        margin: '0px',
        padding: '16px',
        color: 'rgb(255, 255, 255)',
        backgroundColor: 'rgb(0, 0, 0)',
        zIndex: 'auto',
      } as unknown as CSSStyleDeclaration;

      const extracted = extractComputedLayoutStyles(mockStyle);
      expect(extracted.display).toBe('flex');
      expect(extracted.flexDirection).toBe('column');
      expect(extracted.padding).toBe('16px');
      expect(extracted.zIndex).toBeUndefined(); // auto is omitted
    });
  });

  describe('detectSubtreeBranch', () => {
    it('identifies nearest parent with an id', () => {
      const header = document.createElement('header');
      header.id = 'global-header';
      const btn = document.createElement('button');
      header.appendChild(btn);
      document.body.appendChild(header);

      expect(detectSubtreeBranch(btn)).toBe('#global-header');
    });

    it('identifies semantic container tag when no id is present', () => {
      const aside = document.createElement('aside');
      const navItem = document.createElement('a');
      aside.appendChild(navItem);
      document.body.appendChild(aside);

      expect(detectSubtreeBranch(navItem)).toBe('aside');
    });
  });

  describe('partitionPinsBySubtree', () => {
    it('groups pins by their subtree branch key', () => {
      const pins: BrowserAnnotationPin[] = [
        {
          id: 'pin-1',
          index: 1,
          box: { x: 0, y: 0, width: 100, height: 50, viewportWidth: 1000, viewportHeight: 800 },
          comment: 'Fix header alignment',
          createdAt: Date.now(),
          domMetadata: {
            cssSelector: '#navbar > button',
            tagName: 'button',
            classList: [],
            sanitizedOuterHtml: '<button>Login</button>',
            innerText: 'Login',
            computedStyles: {},
            subtreeBranch: 'header',
          },
        },
        {
          id: 'pin-2',
          index: 2,
          box: { x: 0, y: 200, width: 200, height: 300, viewportWidth: 1000, viewportHeight: 800 },
          comment: 'Sidebar background too dark',
          createdAt: Date.now(),
          domMetadata: {
            cssSelector: 'aside > ul',
            tagName: 'ul',
            classList: [],
            sanitizedOuterHtml: '<ul>...</ul>',
            innerText: 'Nav',
            computedStyles: {},
            subtreeBranch: 'aside',
          },
        },
        {
          id: 'pin-3',
          index: 3,
          box: { x: 50, y: 0, width: 100, height: 50, viewportWidth: 1000, viewportHeight: 800 },
          comment: 'Header logo blur',
          createdAt: Date.now(),
          domMetadata: {
            cssSelector: '#navbar > img',
            tagName: 'img',
            classList: [],
            sanitizedOuterHtml: '<img />',
            innerText: '',
            computedStyles: {},
            subtreeBranch: 'header',
          },
        },
      ];

      const groups = partitionPinsBySubtree(pins);
      expect(groups).toHaveLength(2);

      const headerGroup = groups.find((g) => g.subtreeKey === 'header');
      expect(headerGroup).toBeDefined();
      expect(headerGroup?.pins).toHaveLength(2);
      expect(headerGroup?.subtreeName).toBe('Navigation Header');

      const asideGroup = groups.find((g) => g.subtreeKey === 'aside');
      expect(asideGroup).toBeDefined();
      expect(asideGroup?.pins).toHaveLength(1);
      expect(asideGroup?.subtreeName).toBe('Sidebar Panel');
    });
  });
});
