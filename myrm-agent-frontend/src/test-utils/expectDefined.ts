/**
 * [OUTPUT]
 * expectDefined: 断言值非 undefined 并窄化类型。
 * expectNonNull: 断言值非 null 并窄化类型。
 *
 * [POS]
 * 前端测试断言守卫层。为测试提供类型窄化断言函数，收敛测试内的 if-throw 守卫样板。
 *
 * @orphan-ok 测试断言守卫工具，被 src 下多个 __tests__ 测试文件引用（orphan-gate 仅扫描生产代码引用）。
 */

/**
 * 断言值非 undefined，将 T | undefined 窄化为 T。
 * 断言失败抛出携带定位标签的显式错误，CI 失败可直接定位。
 */
export function expectDefined<T>(value: T | undefined, label: string): asserts value is T {
  if (value === undefined) {
    throw new Error(`${label} is undefined`);
  }
}

/**
 * 断言值非 null，将 T | null 窄化为 T。
 * 断言失败抛出携带定位标签的显式错误，CI 失败可直接定位。
 */
export function expectNonNull<T>(value: T | null, label: string): asserts value is T {
  if (value === null) {
    throw new Error(`${label} is null`);
  }
}
