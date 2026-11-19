/**
 * [INPUT]
 * - window.__MYRM_E2E_CHAT__ (POS: `src/types/globals.d.ts` 里桥的类型声明)
 *
 * [OUTPUT]
 * - E2eBridgeMembers: the slice of `window.__MYRM_E2E_CHAT__` one member group provides
 *
 * [POS]
 * 桥成员分组共用的类型：每组工厂返回桥的一个子集，参数类型由桥的全局声明提供。
 */

/** The slice of `window.__MYRM_E2E_CHAT__` one member group provides. */
export type E2eBridgeMembers = Partial<NonNullable<Window['__MYRM_E2E_CHAT__']>>;
