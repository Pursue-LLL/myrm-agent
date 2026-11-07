# test-utils

前端测试共享层。断言守卫收敛各测试文件内的重复 if-throw 样板；真实翻译 mock 让测试能断言最终展示给用户的句子；风控拦截夹具让「被拦下的文字只提示一次」类测试共用同一份响应体与翻译器；假时钟 helper 让防抖 / 轮询类测试在 Testing Library 下可驱动；deferred 让测试在请求进行中观察忙碌态；假凭据 helper 让脱敏类测试在调用时才拼出形似服务商凭据的值。

| 文件               | 地位 | 职责                                                                                                                             | I/O/P |
| ------------------ | ---- | -------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `deferred.ts`      | 核心 | 由测试手动决定何时落定的 Promise（promise / resolve / reject）                                                                   | ✅    |
| `expectDefined.ts` | 核心 | 类型窄化断言守卫（undefined / null 两断言）                                                                                      | ✅    |
| `fakeClock.ts`     | 核心 | 假时钟：`settle` 落地排队更新、`startFakeClock` / `stopFakeClock` 启停可被 Testing Library 驱动的 vitest 时钟、`elapse` 推进时钟 | ✅    |
| `fakeSecrets.ts`   | 核心 | 形似服务商凭据的假值：`openAiStyleKey`、`jwtShaped` 在调用时才拼出前缀，源码里不出现完整令牌，凭据字面量闸门因此不会拦下它们     | ✅    |
| `realIntl.ts`      | 核心 | 以真实语言包构造 next-intl mock（`vi.mock` 工厂内使用，译器按语言与命名空间缓存、引用稳定）                                      | ✅    |
| `riskHeld.ts`      | 核心 | 风控拦截夹具：服务端 400 响应体、英文界面的拦截标题、通知服务的英文翻译器、带 JSON 内容类型的 Response                           | ✅    |
