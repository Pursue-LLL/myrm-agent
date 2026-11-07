/**
 * [OUTPUT]
 * deferred: 由测试手动决定何时落定的 Promise（返回 promise / resolve / reject）。
 *
 * [POS]
 * 前端测试异步控制层。让测试在请求进行中观察忙碌态，再放行请求。
 */

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
