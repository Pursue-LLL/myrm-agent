/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';
import {
  extractDomain,
  isBlankUrl,
  isEligibleHttpUrl,
  isInternalBrowserUrl,
  isNavigationTargetAuthorized,
  isTabAuthorized,
  isTabEligibleForPolicy,
  matchDomain,
} from '../../../../../myrm-agent-extension/src/background/policy.js';

interface Access {
  authorizedDomains: string[];
  allowAllEligibleTabs: boolean;
  pausedTabIds: Set<number>;
  agentTabIds: Set<number>;
}

const access = (overrides: Partial<Access> = {}): Access => ({
  authorizedDomains: [],
  allowAllEligibleTabs: false,
  pausedTabIds: new Set(),
  agentTabIds: new Set(),
  ...overrides,
});

const tab = (id: number, url: string) => ({ id, url });

describe('URL classification', () => {
  it('treats the empty URL and browser-internal schemes as internal', () => {
    for (const url of ['', '  ', 'chrome://settings', 'edge://flags', 'brave://rewards', 'devtools://x', 'chrome-extension://abc/p.html']) {
      expect(isInternalBrowserUrl(url)).toBe(true);
    }
  });

  it('does not treat a blank page or a web page as internal', () => {
    expect(isInternalBrowserUrl('about:blank')).toBe(false);
    expect(isInternalBrowserUrl('https://example.com/')).toBe(false);
  });

  it('recognises a blank page only by an empty URL or about:blank', () => {
    for (const url of ['', '  ', 'about:blank', ' ABOUT:BLANK ']) {
      expect(isBlankUrl(url)).toBe(true);
    }
    for (const url of ['about:newtab', 'https://example.com/', 'data:text/html,<p>x</p>', 'chrome://newtab']) {
      expect(isBlankUrl(url)).toBe(false);
    }
  });

  it('admits http, https and file URLs only', () => {
    expect(isEligibleHttpUrl('https://example.com/a')).toBe(true);
    expect(isEligibleHttpUrl('http://intranet.example:8080/')).toBe(true);
    expect(isEligibleHttpUrl('file:///tmp/report.html')).toBe(true);
    expect(isEligibleHttpUrl('ftp://example.com/')).toBe(false);
    expect(isEligibleHttpUrl('about:blank')).toBe(false);
    expect(isEligibleHttpUrl('not a url')).toBe(false);
  });

  it('extracts the hostname without the port, and nothing from garbage', () => {
    expect(extractDomain('http://intranet.example:8080/path?q=1')).toBe('intranet.example');
    expect(extractDomain('::nonsense::')).toBe('');
  });
});

describe('matchDomain', () => {
  it('matches an exact pattern only exactly', () => {
    expect(matchDomain('example.com', 'example.com')).toBe(true);
    expect(matchDomain('www.example.com', 'example.com')).toBe(false);
  });

  it('lets a wildcard cover the root and every subdomain, but not look-alikes', () => {
    expect(matchDomain('example.com', '*.example.com')).toBe(true);
    expect(matchDomain('a.b.example.com', '*.example.com')).toBe(true);
    expect(matchDomain('evilexample.com', '*.example.com')).toBe(false);
    expect(matchDomain('example.com.evil.test', '*.example.com')).toBe(false);
  });
});

describe('tab eligibility', () => {
  it('admits nothing while no domain is authorized', () => {
    expect(isTabEligibleForPolicy(tab(1, 'https://example.com/'), access())).toBe(false);
  });

  it('admits tabs on authorized domains and nothing else', () => {
    const policy = access({ authorizedDomains: ['example.com'] });
    expect(isTabEligibleForPolicy(tab(1, 'https://example.com/a'), policy)).toBe(true);
    expect(isTabEligibleForPolicy(tab(2, 'https://other.test/'), policy)).toBe(false);
  });

  it('never admits browser-internal pages, even when everything is allowed', () => {
    const policy = access({ allowAllEligibleTabs: true });
    expect(isTabEligibleForPolicy(tab(1, 'chrome://settings'), policy)).toBe(false);
    expect(isTabEligibleForPolicy(tab(2, 'https://anything.test/'), policy)).toBe(true);
    expect(isTabEligibleForPolicy(tab(3, 'ftp://anything.test/'), policy)).toBe(false);
  });

  it('rejects a tab without an integer id', () => {
    const policy = access({ allowAllEligibleTabs: true });
    expect(isTabEligibleForPolicy(undefined, policy)).toBe(false);
    expect(isTabEligibleForPolicy({ url: 'https://example.com/' }, policy)).toBe(false);
  });

  it('withholds a paused tab from the Agent while keeping it eligible for listing', () => {
    const policy = access({ authorizedDomains: ['example.com'], pausedTabIds: new Set([7]) });
    const paused = tab(7, 'https://example.com/');
    expect(isTabEligibleForPolicy(paused, policy)).toBe(true);
    expect(isTabAuthorized(paused, policy)).toBe(false);
    expect(isTabAuthorized(tab(8, 'https://example.com/'), policy)).toBe(true);
  });
});

describe('tabs the Agent opened', () => {
  it('admits a blank tab the Agent opened, even while no domain is authorized', () => {
    const policy = access({ agentTabIds: new Set([5]) });
    expect(isTabEligibleForPolicy(tab(5, 'about:blank'), policy)).toBe(true);
    expect(isTabEligibleForPolicy(tab(5, ''), policy)).toBe(true);
    expect(isTabAuthorized(tab(5, 'about:blank'), policy)).toBe(true);
  });

  it('never admits a blank tab the user opened', () => {
    const policy = access({ agentTabIds: new Set([5]), allowAllEligibleTabs: true });
    expect(isTabEligibleForPolicy(tab(6, 'about:blank'), policy)).toBe(false);
  });

  it('applies the normal policy to an Agent tab once it has left the blank page', () => {
    const policy = access({ agentTabIds: new Set([5]), authorizedDomains: ['example.com'] });
    expect(isTabEligibleForPolicy(tab(5, 'https://example.com/'), policy)).toBe(true);
    expect(isTabEligibleForPolicy(tab(5, 'https://other.test/'), policy)).toBe(false);
    expect(isTabEligibleForPolicy(tab(5, 'chrome://settings'), policy)).toBe(false);
  });

  it('keeps a paused Agent tab away from the Agent', () => {
    const policy = access({ agentTabIds: new Set([5]), pausedTabIds: new Set([5]) });
    expect(isTabEligibleForPolicy(tab(5, 'about:blank'), policy)).toBe(true);
    expect(isTabAuthorized(tab(5, 'about:blank'), policy)).toBe(false);
  });
});

describe('isNavigationTargetAuthorized', () => {
  it('follows the authorized domains', () => {
    const policy = access({ authorizedDomains: ['*.example.com'] });
    expect(isNavigationTargetAuthorized('https://app.example.com/x', policy)).toBe(true);
    expect(isNavigationTargetAuthorized('https://evil.test/', policy)).toBe(false);
  });

  it('refuses internal pages and unparsable targets under any policy', () => {
    const policy = access({ allowAllEligibleTabs: true, authorizedDomains: ['example.com'] });
    expect(isNavigationTargetAuthorized('chrome://settings', policy)).toBe(false);
    expect(isNavigationTargetAuthorized('javascript:alert(1)', policy)).toBe(false);
    expect(isNavigationTargetAuthorized('', policy)).toBe(false);
  });

  it('refuses everything while no domain is authorized and allow-all is off', () => {
    expect(isNavigationTargetAuthorized('https://example.com/', access())).toBe(false);
  });
});
