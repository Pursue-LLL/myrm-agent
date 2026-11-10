/**
 * [INPUT] The `katex` the app loads its stylesheet from, and the `katex` that `rehype-katex` and
 *         `micromark-extension-math` resolve to.
 * [OUTPUT] Vitest: the formula renderer and the stylesheet come from one KaTeX copy.
 * [POS] KaTeX's markup and its stylesheet are released as a pair. A renderer older than the stylesheet draws
 * superscripts at full size and loses roots, vectors, braces and arrows, with no error anywhere. A stale nested copy
 * survives a plain `bun install`, so the failure message names the command that removes it.
 */
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const appRequire = createRequire(import.meta.url);

function katexVersionSeenBy(requireFrom: NodeRequire): string {
  const { version } = requireFrom('katex/package.json') as { version: string };
  return version;
}

describe('KaTeX copies', () => {
  it.each(['rehype-katex', 'micromark-extension-math'])('%s resolves the katex the stylesheet comes from', (pkg) => {
    const seen = katexVersionSeenBy(createRequire(appRequire.resolve(pkg)));

    expect(seen, `${pkg} has its own katex copy: run \`bun install --force\``).toBe(katexVersionSeenBy(appRequire));
  });
});
