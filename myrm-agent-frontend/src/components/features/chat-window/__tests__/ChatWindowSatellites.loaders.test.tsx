/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindowSatellites (POS: 聊天窗口的悬浮入口与抽屉集合，每个入口都是 next/dynamic 懒加载)
 *
 * [OUTPUT]
 * Vitest: 每个懒加载器真实执行后都落在一个可渲染的组件上；导入路径或命名导出一旦被改名，这里先于线上白屏报错。
 *
 * [POS]
 * next/dynamic 只负责收集加载器，不渲染；加载器指向的真实模块照常导入。
 */
import { describe, expect, it, vi } from 'vitest';

interface LoadedModule {
  default?: unknown;
}

const registered = vi.hoisted(() => ({ loaders: [] as Array<() => Promise<LoadedModule>> }));

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<LoadedModule>) => {
    registered.loaders.push(loader);
    return () => null;
  },
}));
vi.mock('../subagent/SubagentDashboard', () => ({ default: () => null }));
vi.mock('@/components/features/desktop-inspector/DesktopControlApprovalOverlay', () => ({ default: () => null }));

import '../ChatWindowSatellites';

/** A React component is a function, or an object wrapping one (memo, forwardRef, lazy). */
const isRenderable = (candidate: unknown): boolean =>
  typeof candidate === 'function' || (typeof candidate === 'object' && candidate !== null);

describe('ChatWindowSatellites lazy loaders', () => {
  it('registers a loader for every satellite', () => {
    expect(registered.loaders.length).toBeGreaterThan(0);
  });

  it('resolves every loader to a renderable component', async () => {
    const loaded = await Promise.all(registered.loaders.map((load) => load()));

    const unrenderable = loaded
      .map((module, index) => ({ index, component: module.default }))
      .filter(({ component }) => !isRenderable(component))
      .map(({ index }) => registered.loaders[index].toString());
    expect(unrenderable).toEqual([]);
  });
});
