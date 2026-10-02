# test-utils

前端测试共享断言守卫层。提供类型窄化断言函数，收敛各测试文件内的重复 if-throw 守卫样板为单一事实源。

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `expectDefined.ts` | 核心 | 类型窄化断言守卫（undefined / null 两断言） | ✅ |
