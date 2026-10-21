// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { findHoverOnlyRevealSites } from '../reveal-contract-scan.ts';

const scan = (jsx: string) => findHoverOnlyRevealSites(`export const X = () => (${jsx});`);

describe('findHoverOnlyRevealSites', () => {
  it('flags a hover-only button as missing both keyboard and touch paths', () => {
    const sites = scan(`<div className="group"><button className="opacity-0 group-hover:opacity-100">x</button></div>`);
    expect(sites).toEqual([{ line: 1, tag: 'button', missing: ['keyboard', 'touch'] }]);
  });

  it('reports only the path that is actually missing', () => {
    const keyboardOnly = scan(
      `<button className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100" />`,
    );
    const touchOnly = scan(`<button className="opacity-0 group-hover:opacity-100 pointer-coarse:opacity-100" />`);
    expect(keyboardOnly[0]?.missing).toEqual(['touch']);
    expect(touchOnly[0]?.missing).toEqual(['keyboard']);
  });

  it('accepts the shared REVEAL_ON_HOVER constant, including inside cn()', () => {
    expect(scan(`<button className={REVEAL_ON_HOVER} />`)).toEqual([]);
    expect(scan(`<button className={cn('size-6', REVEAL_ON_HOVER)} />`)).toEqual([]);
  });

  it('accepts an inline full reveal path, including named groups', () => {
    const inline = `opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100`;
    const named = `opacity-0 group-hover/row:opacity-100 group-focus-within/row:opacity-100 pointer-coarse:opacity-100`;
    expect(scan(`<button className="${inline}" />`)).toEqual([]);
    expect(scan(`<button className="${named}" />`)).toEqual([]);
  });

  it.each(['focus:opacity-100', 'focus-visible:opacity-100', 'focus-within:opacity-100'])(
    'treats %s as a keyboard path',
    (variant) => {
      const sites = scan(
        `<button className="opacity-0 group-hover:opacity-100 ${variant} pointer-coarse:opacity-100" />`,
      );
      expect(sites).toEqual([]);
    },
  );

  it('flags class tokens that sit inside conditional expressions', () => {
    const sites = scan(`<button className={cn('opacity-0', open && 'group-hover:opacity-100')} />`);
    expect(sites).toHaveLength(1);
  });

  it('ignores decorative elements that contain nothing interactive', () => {
    expect(scan(`<span className="opacity-0 group-hover:opacity-100">tip</span>`)).toEqual([]);
    expect(scan(`<ExternalLink className="opacity-0 group-hover:opacity-100" />`)).toEqual([]);
  });

  it('flags a decorative container that wraps an interactive descendant', () => {
    const sites = scan(`<div className="opacity-0 group-hover:opacity-100"><button type="button">x</button></div>`);
    expect(sites).toEqual([{ line: 1, tag: 'div', missing: ['keyboard', 'touch'] }]);
  });

  it.each([
    ['onClick handler', `<div onClick={go} className="opacity-0 group-hover:opacity-100" />`],
    ['button role', `<div role="button" className="opacity-0 group-hover:opacity-100" />`],
    ['Button wrapper', `<Button className="opacity-0 group-hover:opacity-100" />`],
    ['namespaced trigger', `<Primitive.Trigger className="opacity-0 group-hover:opacity-100" />`],
    ['router Link', `<Link href="/" className="opacity-0 group-hover:opacity-100" />`],
  ])('treats %s as interactive', (_label, jsx) => {
    expect(scan(jsx)).toHaveLength(1);
  });

  it('ignores variant-prefixed hiding and elements that are never hidden', () => {
    expect(scan(`<button className="md:opacity-0 group-hover:opacity-100" />`)).toEqual([]);
    expect(scan(`<button className="hover:opacity-0 group-hover:opacity-100" />`)).toEqual([]);
    expect(scan(`<button className="opacity-50 group-hover:opacity-100" />`)).toEqual([]);
    expect(scan(`<button className="opacity-0" />`)).toEqual([]);
  });

  it('reports the 1-based line of the opening tag', () => {
    const source = [
      'export const X = () => (',
      '  <div>',
      '    <button',
      '      className="opacity-0 group-hover:opacity-100"',
      '    />',
      '  </div>',
      ');',
    ].join('\n');
    expect(findHoverOnlyRevealSites(source)[0]?.line).toBe(3);
  });
});
