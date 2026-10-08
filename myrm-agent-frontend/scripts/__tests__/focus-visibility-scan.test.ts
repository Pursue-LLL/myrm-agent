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

  it('does not accept no-op focus styles (ring-0, ring-offset, transparent) as a replacement', () => {
    expect(findInvisibleFocusSites(`<button className="outline-none focus-visible:ring-0" />`)).toHaveLength(1);
    expect(findInvisibleFocusSites(`<button className="outline-none focus-visible:ring-offset-2" />`)).toHaveLength(1);
    expect(findInvisibleFocusSites(`<button className="outline-none focus:border-transparent" />`)).toHaveLength(1);
    expect(
      findInvisibleFocusSites(`<button className="outline-none focus-visible:ring-0 focus-visible:ring-2" />`),
    ).toEqual([]);
  });

  it('treats outline-hidden and outline-0 like outline-none', () => {
    expect(findInvisibleFocusSites(`<button className="focus:outline-hidden" />`)).toHaveLength(1);
    expect(findInvisibleFocusSites(`<button className="outline-0" />`)).toHaveLength(1);
    expect(findInvisibleFocusSites(`<button className="focus:outline-hidden focus-visible:ring-1" />`)).toEqual([]);
  });

  it('flags Tabs content panels because they are tabIndex=0 tab stops', () => {
    expect(
      findInvisibleFocusSites(`<TabsContent className="focus-visible:outline-none focus-visible:ring-0" />`),
    ).toHaveLength(1);
    expect(findInvisibleFocusSites(`<TabsPrimitive.Content className="outline-none" />`)).toHaveLength(1);
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
