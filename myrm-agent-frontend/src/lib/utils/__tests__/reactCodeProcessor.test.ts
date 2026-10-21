import { describe, it, expect } from 'vitest';
import {
  isValidReactCode,
  extractUsedHooks,
  detectOptionalDependencies,
  removeReactImport,
  generateReactImport,
  wrapCodeAsApp,
} from '../reactCodeProcessor';

describe('isValidReactCode', () => {
  it('recognizes code with React import and JSX', () => {
    const code = `import React from 'react';\nexport default function App() { return <div>Hello</div>; }`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('recognizes code with named import and JSX', () => {
    const code = `import { useState } from 'react';\nexport function Counter() { return <button>0</button>; }`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('recognizes code with JSX but no React import (auto-import)', () => {
    const code = `export default function Card() { return <div className="card"><h1>Title</h1></div>; }`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('recognizes code with only uppercase JSX tags', () => {
    const code = `function MyComponent() { return <MyButton onClick={fn} />; }`;
    expect(isValidReactCode(code)).toBe(true);
  });

  it('rejects plain JavaScript without JSX', () => {
    const code = `export function add(a, b) { return a + b; }`;
    expect(isValidReactCode(code)).toBe(false);
  });

  it('rejects empty string', () => {
    expect(isValidReactCode('')).toBe(false);
  });

  it('rejects CSS code', () => {
    const code = `.container { display: flex; justify-content: center; }`;
    expect(isValidReactCode(code)).toBe(false);
  });

  it('rejects JSON data', () => {
    const code = `{"name": "test", "version": "1.0.0"}`;
    expect(isValidReactCode(code)).toBe(false);
  });

  it('recognizes TSX with type annotations', () => {
    const code = `import React from 'react';\ninterface Props { title: string; }\nexport const Card: React.FC<Props> = ({ title }) => <div>{title}</div>;`;
    expect(isValidReactCode(code)).toBe(true);
  });
});

describe('extractUsedHooks', () => {
  it('extracts useState and useEffect', () => {
    const code = `const [count, setCount] = useState(0);\nuseEffect(() => {}, []);`;
    const hooks = extractUsedHooks(code);
    expect(hooks).toContain('useState');
    expect(hooks).toContain('useEffect');
    expect(hooks).not.toContain('useCallback');
  });

  it('extracts multiple hooks', () => {
    const code = `
      const ref = useRef(null);
      const memoized = useMemo(() => compute(), [dep]);
      const cb = useCallback(() => {}, []);
    `;
    const hooks = extractUsedHooks(code);
    expect(hooks).toEqual(expect.arrayContaining(['useRef', 'useMemo', 'useCallback']));
  });

  it('returns empty array when no hooks used', () => {
    const code = `function App() { return <div>Hello</div>; }`;
    expect(extractUsedHooks(code)).toHaveLength(0);
  });

  it('detects useReducer and useContext', () => {
    const code = `const [state, dispatch] = useReducer(reducer, init);\nconst ctx = useContext(MyContext);`;
    const hooks = extractUsedHooks(code);
    expect(hooks).toContain('useReducer');
    expect(hooks).toContain('useContext');
  });

  it('detects newer hooks like useId and useTransition', () => {
    const code = `const id = useId();\nconst [isPending, startTransition] = useTransition();`;
    const hooks = extractUsedHooks(code);
    expect(hooks).toContain('useId');
    expect(hooks).toContain('useTransition');
  });
});

describe('detectOptionalDependencies', () => {
  it('detects Radix UI imports', () => {
    const code = `import { Dialog } from '@radix-ui/react-dialog';\nimport { Tabs } from '@radix-ui/react-tabs';`;
    const deps = detectOptionalDependencies(code);
    expect(deps).toHaveProperty('@radix-ui/react-dialog');
    expect(deps).toHaveProperty('@radix-ui/react-tabs');
  });

  it('detects axios import', () => {
    const code = `import axios from 'axios';\naxios.get('/api/data');`;
    const deps = detectOptionalDependencies(code);
    expect(deps).toHaveProperty('axios');
  });

  it('returns empty for code with no optional deps', () => {
    const code = `import React from 'react';\nfunction App() { return <div>Hello</div>; }`;
    const deps = detectOptionalDependencies(code);
    expect(Object.keys(deps)).toHaveLength(0);
  });

  it('detects nanoid import', () => {
    const code = `import { nanoid } from 'nanoid';\nconst id = nanoid();`;
    const deps = detectOptionalDependencies(code);
    expect(deps).toHaveProperty('nanoid');
  });

  it('detects multiple Radix primitives in a complex component', () => {
    const code = `
      import { Select } from '@radix-ui/react-select';
      import { Popover } from '@radix-ui/react-popover';
      import { Tooltip } from '@radix-ui/react-tooltip';
    `;
    const deps = detectOptionalDependencies(code);
    expect(Object.keys(deps)).toHaveLength(3);
    expect(deps).toHaveProperty('@radix-ui/react-select');
    expect(deps).toHaveProperty('@radix-ui/react-popover');
    expect(deps).toHaveProperty('@radix-ui/react-tooltip');
  });
});

describe('removeReactImport', () => {
  it('removes default React import', () => {
    const code = `import React from 'react';\nfunction App() { return <div />; }`;
    expect(removeReactImport(code)).toBe('function App() { return <div />; }');
  });

  it('removes React import with named exports', () => {
    const code = `import React, { useState, useEffect } from 'react';\nfunction App() {}`;
    expect(removeReactImport(code)).toBe('function App() {}');
  });

  it('removes namespace import', () => {
    const code = `import * as React from 'react';\nconst App = () => <div />;`;
    expect(removeReactImport(code)).toBe('const App = () => <div />;');
  });

  it('removes named-only import', () => {
    const code = `import { useState } from 'react';\nfunction Counter() {}`;
    expect(removeReactImport(code)).toBe('function Counter() {}');
  });

  it('preserves non-React imports', () => {
    const code = `import React from 'react';\nimport axios from 'axios';\nfunction App() {}`;
    const result = removeReactImport(code);
    expect(result).toContain("import axios from 'axios'");
    expect(result).not.toContain("from 'react'");
  });
});

describe('generateReactImport', () => {
  it('generates basic import when no hooks used', () => {
    const code = `function App() { return <div>Hello</div>; }`;
    expect(generateReactImport(code)).toBe("import React from 'react';");
  });

  it('generates import with useState', () => {
    const code = `const [x, setX] = useState(0);`;
    expect(generateReactImport(code)).toBe("import React, { useState } from 'react';");
  });

  it('generates import with multiple hooks', () => {
    const code = `useState(0); useEffect(() => {}); useRef(null);`;
    const result = generateReactImport(code);
    expect(result).toContain('useState');
    expect(result).toContain('useEffect');
    expect(result).toContain('useRef');
  });
});

describe('wrapCodeAsApp', () => {
  it('preserves code that already has export default App', () => {
    const code = `import React from 'react';\nexport default function App() { return <div>Hello</div>; }`;
    const result = wrapCodeAsApp(code, 'App.tsx');
    expect(result).toContain('export default function App()');
    expect(result).toContain('Hello');
  });

  it('wraps export default component as App', () => {
    const code = `import React from 'react';\nfunction Dashboard() { return <div>Dashboard</div>; }\nexport default Dashboard;`;
    const result = wrapCodeAsApp(code, 'Dashboard.tsx');
    expect(result).toContain('export default function App()');
    expect(result).toContain('<Dashboard />');
  });

  it('wraps named export component as App', () => {
    const code = `import React from 'react';\nexport function Card() { return <div>Card</div>; }`;
    const result = wrapCodeAsApp(code, 'Card.tsx');
    expect(result).toContain('export default function App()');
    expect(result).toContain('<Card />');
  });

  it('wraps component without export as App', () => {
    const code = `function Button() { return <button>Click</button>; }`;
    const result = wrapCodeAsApp(code, 'Button.tsx');
    expect(result).toContain('export default function App()');
    expect(result).toContain('<Button />');
  });

  it('wraps bare JSX fragment as App', () => {
    const code = `<h1>Hello World</h1>`;
    const result = wrapCodeAsApp(code, 'fragment.tsx');
    expect(result).toContain('export default function App()');
    expect(result).toContain('<h1>Hello World</h1>');
  });

  it('includes original code marker for extraction', () => {
    const code = `import React from 'react';\nexport default function App() { return <div />; }`;
    const result = wrapCodeAsApp(code, 'App.tsx');
    expect(result).toContain('BEGIN ORIGINAL CODE');
    expect(result).toContain('END ORIGINAL CODE');
  });

  it('adds correct React import with hooks', () => {
    const code = `export default function Timer() { const [t, setT] = useState(0); useEffect(() => {}, []); return <span>{t}</span>; }`;
    const result = wrapCodeAsApp(code, 'Timer.tsx');
    expect(result).toContain('useState');
    expect(result).toContain('useEffect');
  });

  it('handles const arrow function components', () => {
    const code = `const Hero = () => <section><h1>Welcome</h1></section>;\nexport default Hero;`;
    const result = wrapCodeAsApp(code, 'Hero.tsx');
    expect(result).toContain('export default function App()');
    expect(result).toContain('<Hero />');
  });
});
