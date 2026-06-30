import { describe, it, expect } from 'vitest';

import {
  isValidReactCode,
  extractUsedHooks,
  detectOptionalDependencies,
  removeReactImport,
  generateReactImport,
  wrapCodeAsApp,
} from '@/lib/utils/reactCodeProcessor';

describe('isValidReactCode', () => {
  it('recognizes code with React import and export', () => {
    const code = `import React from 'react';\nexport default function App() { return <div />; }`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('recognizes code with uppercase JSX component tag', () => {
    const code = `export const App = () => <Button>Click</Button>;`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('recognizes code with HTML tag containing attributes', () => {
    const code = `export const App = () => <div className="test">Hello</div>;`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('recognizes code with JSX tags only (no export)', () => {
    const code = `const App = () => <div className="test">Hello</div>;`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('rejects plain JavaScript without JSX or React', () => {
    const code = `const x = 42;\nconsole.log(x);`;
    expect(isValidReactCode(code)).toBe(false);
  });

  it('rejects empty string', () => {
    expect(isValidReactCode('')).toBe(false);
  });
});

describe('extractUsedHooks', () => {
  it('extracts useState and useEffect', () => {
    const code = `import { useState, useEffect } from 'react';`;
    const hooks = extractUsedHooks(code);
    expect(hooks).toContain('useState');
    expect(hooks).toContain('useEffect');
    expect(hooks).not.toContain('useCallback');
  });

  it('returns empty array when no hooks used', () => {
    const code = `const App = () => <div />;`;
    expect(extractUsedHooks(code)).toEqual([]);
  });

  it('detects hooks used in function body', () => {
    const code = `function App() { const [x, setX] = useState(0); return <div>{x}</div>; }`;
    expect(extractUsedHooks(code)).toContain('useState');
  });
});

describe('detectOptionalDependencies', () => {
  it('detects @radix-ui/react-dialog import', () => {
    const code = `import { Dialog } from '@radix-ui/react-dialog';`;
    const deps = detectOptionalDependencies(code);
    expect(deps).toHaveProperty('@radix-ui/react-dialog');
  });

  it('detects axios import', () => {
    const code = `import axios from 'axios';`;
    const deps = detectOptionalDependencies(code);
    expect(deps).toHaveProperty('axios');
  });

  it('returns empty for code without optional deps', () => {
    const code = `import React from 'react';`;
    const deps = detectOptionalDependencies(code);
    expect(Object.keys(deps)).toHaveLength(0);
  });

  it('detects multiple optional deps', () => {
    const code = `
import { Dialog } from '@radix-ui/react-dialog';
import { v4 } from 'uuid';
`;
    const deps = detectOptionalDependencies(code);
    expect(deps).toHaveProperty('@radix-ui/react-dialog');
    expect(deps).toHaveProperty('uuid');
  });
});

describe('removeReactImport', () => {
  it('removes default React import', () => {
    const code = `import React from 'react';\nconst App = () => <div />;`;
    const result = removeReactImport(code);
    expect(result).not.toContain("import React from 'react'");
    expect(result).toContain('const App');
  });

  it('removes named React imports', () => {
    const code = `import React, { useState, useEffect } from 'react';\nconst App = () => <div />;`;
    const result = removeReactImport(code);
    expect(result).not.toContain('import React');
    expect(result).toContain('const App');
  });

  it('removes namespace import', () => {
    const code = `import * as React from 'react';\nconst App = () => <div />;`;
    const result = removeReactImport(code);
    expect(result).not.toContain('import * as React');
  });

  it('preserves non-React imports', () => {
    const code = `import React from 'react';\nimport axios from 'axios';\nconst App = () => <div />;`;
    const result = removeReactImport(code);
    expect(result).toContain("import axios from 'axios'");
  });
});

describe('generateReactImport', () => {
  it('generates import with hooks when hooks are used', () => {
    const code = `function App() { const [x] = useState(0); useEffect(() => {}, []); }`;
    const result = generateReactImport(code);
    expect(result).toContain('useState');
    expect(result).toContain('useEffect');
    expect(result).toContain('React');
  });

  it('generates plain React import when no hooks used', () => {
    const code = `const App = () => <div />;`;
    const result = generateReactImport(code);
    expect(result).toBe(`import React from 'react';`);
  });
});

describe('wrapCodeAsApp', () => {
  it('wraps code that already has export default App', () => {
    const code = `import React from 'react';\nexport default function App() { return <div>Hello</div>; }`;
    const result = wrapCodeAsApp(code, 'test.tsx');
    expect(result).toContain('export default function App');
    expect(result).toContain('BEGIN ORIGINAL CODE');
  });

  it('wraps a named component with export default', () => {
    const code = `import React from 'react';\nexport default function Button() { return <button>Click</button>; }`;
    const result = wrapCodeAsApp(code, 'Button.tsx');
    expect(result).toContain('export default function App');
    expect(result).toContain('<Button />');
  });

  it('wraps a named export component', () => {
    const code = `import React from 'react';\nexport const Card = () => <div className="card">Content</div>;`;
    const result = wrapCodeAsApp(code, 'Card.tsx');
    expect(result).toContain('export default function App');
    expect(result).toContain('<Card />');
  });

  it('wraps a component without export', () => {
    const code = `import React from 'react';\nconst Header = () => <header>Nav</header>;`;
    const result = wrapCodeAsApp(code, 'Header.tsx');
    expect(result).toContain('export default function App');
    expect(result).toContain('<Header />');
  });

  it('wraps plain JSX fragment', () => {
    const code = `<h1>Hello World</h1>`;
    const result = wrapCodeAsApp(code, 'snippet.tsx');
    expect(result).toContain('export default function App');
    expect(result).toContain('<h1>Hello World</h1>');
  });
});
