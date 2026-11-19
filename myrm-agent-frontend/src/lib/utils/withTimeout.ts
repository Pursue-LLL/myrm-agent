/**
 * [INPUT]
 * (None)
 *
 * [OUTPUT]
 * withTimeout: 给 Promise 加等待上限；上限内落定则原样返回，超时以 Error 拒绝。
 *
 * [POS]
 * 「前置查询不得卡住后续动作」的通用等待上限。底层操作不会被取消，超时之后到达的结果（含拒绝）被丢弃；
 * 超时之后的去向（放行、降级、报错）由调用方在 catch 里决定。
 */
export function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`timed out after ${ms} ms`)), ms);
    promise.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}
