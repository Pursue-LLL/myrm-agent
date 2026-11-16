import { describe, expect, it } from 'vitest';

import {
  findChannelTextLines,
  findDevBridgeImports,
  findUnguardedE2eChannelSites,
  scanE2eChannelSites,
} from '../e2e-channel-scan.ts';

const unguarded = (source: string) => findUnguardedE2eChannelSites(source, 'src/sample.tsx');

describe('scanE2eChannelSites: what counts as a channel reference', () => {
  it('recognizes window handles, storage keys, event names, script ids and bridge mounts', () => {
    const sites = scanE2eChannelSites(
      `
      (window as W).__myrmChatStore = store;
      const a = window.__MYRM_E2E_RUNTIME__?.apiBase;
      const b = window['__MYRM_E2E_API_BASE__'];
      const c = sessionStorage.getItem('e2e_warm_platform_readiness');
      window.addEventListener('myrm-e2e-chat-route-hydrated', onHydrated);
      window.addEventListener('myrm_e2e_runtime_ready', resync);
      const d = <Script id="e2e-runtime-bootstrap" />;
      const e = <E2eBridgeLoader />;
      const f = <E2ECompanionBridge />;
      const g = <><E2EChatBridge /><E2EWikiBridge /></>;
      delete window.__wikiMarkdownEditor;
      const probe = await fetch(\`/security/allowlist/test/hitl-probe?chat_id=\${chatId}\`);
      const other = await fetch('/api/test/seed');
      Object.defineProperty(window, '__MYRM_E2E_CHAT__', { value: 1 });
      const present = '__myrmChatStore' in window;
    `,
      'src/sample.tsx',
    );

    expect(sites.map(({ kind, name }) => `${kind}:${name}`)).toEqual([
      'global:__myrmChatStore',
      'global:__MYRM_E2E_RUNTIME__',
      'global:__MYRM_E2E_API_BASE__',
      'string:e2e_warm_platform_readiness',
      'string:myrm-e2e-chat-route-hydrated',
      'string:myrm_e2e_runtime_ready',
      'string:e2e-runtime-bootstrap',
      'bridge:E2eBridgeLoader',
      'bridge:E2ECompanionBridge',
      'bridge:E2EChatBridge',
      'bridge:E2EWikiBridge',
      'global:__wikiMarkdownEditor',
      'string:/security/allowlist/test/hitl-probe?chat_id=',
      'string:/api/test/seed',
      'string:__MYRM_E2E_CHAT__',
      'string:__myrmChatStore',
    ]);
  });

  it('reports the line of each reference', () => {
    const sites = scanE2eChannelSites(
      `const a = 1;\n\nwindow.__myrmChatStore = 1;\nwindow.__myrmSubagentStore = 2;`,
      'a.ts',
    );

    expect(sites.map(({ line }) => line)).toEqual([3, 4]);
  });

  it('leaves platform globals, product internals and type-only mentions alone', () => {
    const sites = scanE2eChannelSites(
      `
      const a = window.__TAURI__;
      const b = window.__threeStats;
      const c = 'e2ee_key_exchange';
      const cron = fetch(\`/cron/\${id}/test-delivery\`);
      const token = '__myrm_local_no_auth__';
      const d = <div data-testid="chat-input" />;
      type Key = 'e2e_warm_platform_readiness';
      declare global { interface Window { __MYRM_E2E_API_BASE__?: string } }
      import { x } from '@/components/dev/e2eBridge/x';
    `,
      'src/sample.tsx',
    );

    expect(sites).toEqual([]);
  });
});

describe('scanE2eChannelSites: reference forms beyond a window member access', () => {
  it.each([
    ['an object literal key', `Object.assign(window, { __myrmChatStore: store });`, ['global:__myrmChatStore']],
    ['a shorthand property, reported once', `Object.assign(window, { __myrmChatStore });`, ['global:__myrmChatStore']],
    ['a destructured name', `const { __myrmChatStore } = window;`, ['global:__myrmChatStore']],
    ['a destructured name with a default', `const { __myrmChatStore = null } = window;`, ['global:__myrmChatStore']],
    ['a bare identifier', `if (typeof __MYRM_E2E_API_BASE__ !== 'undefined') run();`, ['global:__MYRM_E2E_API_BASE__']],
    ['an identifier under a value assertion', `const s = __myrmChatStore as Store;`, ['global:__myrmChatStore']],
    [
      'a marker inside inline script text',
      `const code = "window.__MYRM_E2E_RUNTIME__ = {};";`,
      ['string:window.__MYRM_E2E_RUNTIME__ = {};'],
    ],
    [
      'a marker inside a template script',
      'const code = `window.__myrmChatStore = ${value};`;',
      ['string:window.__myrmChatStore = '],
    ],
    [
      'a script address',
      `const el = <Script src="/e2e-runtime-bootstrap.js" />;`,
      ['string:/e2e-runtime-bootstrap.js'],
    ],
  ])('records %s', (_label, source, expected) => {
    const sites = scanE2eChannelSites(source, 'src/sample.tsx');

    expect(sites.map(({ kind, name }) => `${kind}:${name}`)).toEqual(expected);
  });

  it('leaves type positions and product words that only resemble a marker alone', () => {
    const sites = scanE2eChannelSites(
      `
      type Handles = { __myrmChatStore: unknown };
      interface Probe { __MYRM_E2E_CHAT__?: object }
      const w = window as Window & { __MYRM_E2E_CHAT__?: object };
      const sentinel = 'prefix __myrm_local_no_auth__ suffix';
      const word = 'pre_e2e_value';
    `,
      'src/sample.tsx',
    );

    expect(sites).toEqual([]);
  });
});

describe('scanE2eChannelSites: guarded references', () => {
  it.each([
    ['an if branch', `if (process.env.NODE_ENV !== 'production') { window.__myrmA = 1; }`],
    ['a loose comparison', `if (process.env.NODE_ENV != 'production') { window.__myrmA = 1; }`],
    ['a reversed comparison', `if ('production' !== process.env.NODE_ENV) { window.__myrmA = 1; }`],
    ['a parenthesized test', `if ((process.env.NODE_ENV !== 'production')) { window.__myrmA = 1; }`],
    [
      'a conjunction with another test',
      `if (typeof window !== 'undefined' && process.env.NODE_ENV !== 'production') { window.__myrmA = 1; }`,
    ],
    [
      'the right operand of a guarded conjunction inside the test',
      `if (process.env.NODE_ENV !== 'production' && typeof window !== 'undefined' && window.__myrmA) { run(); }`,
    ],
    ['a guarded && expression', `process.env.NODE_ENV !== 'production' && (window.__myrmA = 1);`],
    ['a production || expression', `const v = process.env.NODE_ENV === 'production' || window.__myrmA;`],
    ['the live arm of a ternary', `const v = process.env.NODE_ENV !== 'production' ? window.__myrmA : null;`],
    [
      'the dead arm of a production ternary',
      `const v = process.env.NODE_ENV === 'production' ? null : window.__myrmA;`,
    ],
    [
      'the else branch of a production test',
      `if (process.env.NODE_ENV === 'production') { noop(); } else { window.__myrmA = 1; }`,
    ],
    ['an early return', `function f() { if (process.env.NODE_ENV === 'production') { return; } window.__myrmA = 1; }`],
    [
      'an early return without a block',
      `function f(id) { if (!id || process.env.NODE_ENV === 'production') return; window.__myrmA = 1; }`,
    ],
    [
      'a closure created after an early return',
      `function f() { if (process.env.NODE_ENV === 'production') { return; } return () => window.removeEventListener('myrm-e2e-x', h); }`,
    ],
    [
      'a component that returns early in production',
      `function Loader() { if (process.env.NODE_ENV === 'production' || !isLocalDevHost()) { return null; } return <><E2EChatBridge /><E2EWikiBridge /></>; }`,
    ],
    ['a guarded JSX mount', `const el = <div>{process.env.NODE_ENV !== 'production' && <E2eBridgeLoader />}</div>;`],
    [
      'an object literal key behind an if',
      `if (process.env.NODE_ENV !== 'production') { Object.assign(window, { __myrmChatStore }); }`,
    ],
    [
      'a destructuring after an early return',
      `function f() { if (process.env.NODE_ENV === 'production') { return; } const { __myrmChatStore } = window; }`,
    ],
    [
      'a guarded script tag',
      `const el = <div>{process.env.NODE_ENV !== 'production' && <Script src="/e2e-runtime-bootstrap.js" />}</div>;`,
    ],
  ])('treats %s as guarded', (_label, source) => {
    const sites = scanE2eChannelSites(source, 'src/sample.tsx');

    expect(sites.length).toBeGreaterThan(0);
    expect(sites.every(({ guarded }) => guarded)).toBe(true);
  });
});

describe('scanE2eChannelSites: unguarded references', () => {
  it.each([
    ['a bare assignment', `window.__myrmA = 1;`],
    ['the production branch itself', `if (process.env.NODE_ENV === 'production') { window.__myrmA = 1; }`],
    [
      'the dead arm of a development ternary',
      `const v = process.env.NODE_ENV !== 'production' ? null : window.__myrmA;`,
    ],
    [
      'the else branch of a development test',
      `if (process.env.NODE_ENV !== 'production') { ok(); } else { window.__myrmA = 1; }`,
    ],
    ['a test against another environment', `if (process.env.NODE_ENV === 'development') { window.__myrmA = 1; }`],
    ['an exclusion of another environment', `if (process.env.NODE_ENV !== 'test') { window.__myrmA = 1; }`],
    [
      'a disjunction that production can still satisfy',
      `if (process.env.NODE_ENV !== 'production' || flag) { window.__myrmA = 1; }`,
    ],
    [
      'an early return that production only sometimes takes',
      `function f() { if (process.env.NODE_ENV === 'production' && flag) { return; } window.__myrmA = 1; }`,
    ],
    [
      'an early-return test whose body does not return',
      `function f() { if (process.env.NODE_ENV === 'production') { log(); } window.__myrmA = 1; }`,
    ],
    [
      'a reference ahead of the early return',
      `function f() { window.__myrmA = 1; if (process.env.NODE_ENV === 'production') { return; } }`,
    ],
    [
      'the left operand of a guarded conjunction',
      `if (window.__myrmA && process.env.NODE_ENV !== 'production') { run(); }`,
    ],
    [
      'a function whose only guard is at its call site',
      `const stop = process.env.NODE_ENV === 'production' ? undefined : follow();
       function follow() { window.addEventListener('myrm_e2e_runtime_ready', resync); }`,
    ],
    [
      'a production flag kept in a variable',
      `const isProd = process.env.NODE_ENV === 'production'; if (!isProd) { window.__myrmA = 1; }`,
    ],
    ['a computed environment read', `if (process.env['NODE_ENV'] !== 'production') { window.__myrmA = 1; }`],
    ['an unguarded bridge mount', `const el = <E2eBridgeLoader />;`],
    ['a development-host guard function', `if (isLocalDevHost()) { window.__myrmA = 1; }`],
    [
      'a negated development-host early return',
      `function f() { if (!isLocalDevHost()) { return; } window.__myrmA = 1; }`,
    ],
    ['an E2E binding guard function', `if (resolveE2eApiBase()) { window.__myrmA = 1; }`],
    [
      'a component that only checks the host',
      `function Loader() { if (!isLocalDevHost()) { return null; } return <><E2EChatBridge /><E2EWikiBridge /></>; }`,
    ],
    ['a test route in a template literal', 'const url = `/security/allowlist/test/hitl-probe?chat_id=${id}`;'],
    ['a shorthand property', `Object.assign(window, { __myrmChatStore });`],
    ['a destructured name', `const { __myrmChatStore } = window;`],
    ['an unguarded script tag', `const el = <Script src="/e2e-runtime-bootstrap.js" />;`],
    ['a marker inside inline script text', `const code = "window.__MYRM_E2E_RUNTIME__ = {};";`],
  ])('flags %s', (_label, source) => {
    expect(unguarded(source).length).toBeGreaterThan(0);
  });

  it('flags only the references that escape the guard, with their lines', () => {
    const sites = unguarded(`if (process.env.NODE_ENV !== 'production') {
  window.__myrmChatStore = store;
}
window.__myrmSubagentStore = other;`);

    expect(sites).toEqual([{ line: 4, kind: 'global', name: '__myrmSubagentStore', guarded: false }]);
  });
});

describe('findDevBridgeImports', () => {
  const imports = (source: string, fileName: string) => findDevBridgeImports(source, fileName);

  it('flags the bridge modules imported through the alias, relative paths, dynamic imports and re-exports', () => {
    expect(
      imports(
        `
        import Loader from '@/components/dev/E2eBridgeLoader';
        import { createE2eChatBridge } from '../dev/e2eBridge/members/createE2eChatBridge';
        export { Companion } from '@/components/dev/E2ECompanionBridge';
        const lazy = () => import('@/components/dev/E2EWikiBridge');
      `,
        'src/components/layout/AppLayout.tsx',
      ),
    ).toEqual([
      '@/components/dev/E2eBridgeLoader',
      '../dev/e2eBridge/members/createE2eChatBridge',
      '@/components/dev/E2ECompanionBridge',
      '@/components/dev/E2EWikiBridge',
    ]);
  });

  it('resolves a relative path against the importing file', () => {
    expect(imports(`import X from '../components/dev/E2eBridgeLoader';`, 'src/app/layout.tsx')).toEqual([
      '../components/dev/E2eBridgeLoader',
    ]);
    expect(imports(`import X from '../dev/E2ECompanionBridge';`, 'src/components/layout/AppLayout.tsx')).toEqual([
      '../dev/E2ECompanionBridge',
    ]);
  });

  it('lets the leaf development-host guard through', () => {
    expect(
      imports(`import { isLocalDevHost } from '@/components/dev/localDevHost';`, 'src/components/features/x.tsx'),
    ).toEqual([]);
  });

  it('leaves packages, sibling directories and unrelated relative paths alone', () => {
    expect(
      imports(
        `
        import { x } from 'react';
        import { y } from '@/components/devtools/Panel';
        import { z } from './dev-helpers';
        import { w } from '../lib/dev/thing';
      `,
        'src/components/features/x.tsx',
      ),
    ).toEqual([]);
  });
});

describe('findChannelTextLines', () => {
  it('reports each line that carries a marker once, however many markers it holds', () => {
    const source = [
      'const a = 1;',
      `window.__MYRM_E2E_RUNTIME__ = window.__MYRM_E2E_API_BASE__ = 'x';`,
      'run();',
      `const prefix = 'myrm-e2e-v1:';`,
    ].join('\n');

    expect(findChannelTextLines(source)).toEqual([2, 4]);
  });

  it('counts storage keys and the bootstrap address, which an asset cannot guard', () => {
    const source = [`sessionStorage.setItem('e2e_flag', '1');`, `<script src="/e2e-runtime-bootstrap.js"></script>`];

    expect(findChannelTextLines(source.join('\r\n'))).toEqual([1, 2]);
  });

  it('leaves ordinary asset text alone', () => {
    const source = [
      `{"name":"Myrm","icons":[{"src":"/icons/icon-192x192.png"}]}`,
      `window.matchMedia('(prefers-color-scheme: dark)');`,
      `const sentinel = '__myrm_local_no_auth__';`,
      `const word = 'e2ee_key_exchange';`,
    ];

    expect(findChannelTextLines(source.join('\n'))).toEqual([]);
  });
});
