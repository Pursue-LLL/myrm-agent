// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { findInvisibleFocusSites } from '../focus-visibility-scan';

describe('findInvisibleFocusSites', () => {
  it('flags a button whose outline-none has no visible focus replacement', () => {
    const source = `<button type="button" className="px-2 outline-none">Go</button>`;
    expect(findInvisibleFocusSites(source)).toEqual([{ line: 1, tag: 'button' }]);
  });

  it('accepts a replacement declared in another cn() argument of the same className', () => {
    const source = `
      <button
        className={cn(
          'px-2 outline-none',
          active ? 'bg-accent' : '',
          'focus-visible:ring-2 focus-visible:ring-ring',
        )}
      />`;
    expect(findInvisibleFocusSites(source)).toEqual([]);
  });

  it('accepts focus:border / focus:ring replacements and focus-visible:outline-none with ring', () => {
    expect(findInvisibleFocusSites(`<button className="outline-none focus:border-primary" />`)).toEqual([]);
    expect(findInvisibleFocusSites(`<button className="focus-visible:outline-none focus-visible:ring-1" />`)).toEqual(
      [],
    );
  });

  it('treats focus:outline-none as the offender, not as a replacement', () => {
    expect(findInvisibleFocusSites(`<button className="focus:outline-none" />`)).toHaveLength(1);
  });

  it('reports the line of the outline-none token inside a multi-line template className', () => {
    const source = ['<button', '  className={`px-2', '    outline-none`}', '/>'].join('\n');
    expect(findInvisibleFocusSites(source)).toEqual([{ line: 3, tag: 'button' }]);
  });

  it('exempts text inputs, media, Radix content containers and cmdk selected items', () => {
    expect(findInvisibleFocusSites(`<input className="outline-none" />`)).toEqual([]);
    expect(findInvisibleFocusSites(`<TextareaAutosize className="focus:outline-none" />`)).toEqual([]);
    expect(findInvisibleFocusSites(`<audio className="outline-none" />`)).toEqual([]);
    expect(findInvisibleFocusSites(`<PopoverPrimitive.Content className="outline-none" />`)).toEqual([]);
    expect(findInvisibleFocusSites(`<Item className="outline-none data-[selected=true]:bg-accent" />`)).toEqual([]);
  });

  it('exempts elements that cannot be reached by Tab (tabIndex={-1})', () => {
    const source = `<div ref={ref} tabIndex={-1} className={cn('flex', 'focus:outline-none')} />`;
    expect(findInvisibleFocusSites(source)).toEqual([]);
  });

  it('does not let an arrow function inside the opening tag end tag parsing early', () => {
    const source = `<button onClick={() => go()} className="outline-none">x</button>`;
    expect(findInvisibleFocusSites(source)).toHaveLength(1);
  });

  it('ignores outline-none outside className attributes', () => {
    expect(findInvisibleFocusSites(`const x = 'outline-none';\n<button className="p-2" />`)).toEqual([]);
  });
});
