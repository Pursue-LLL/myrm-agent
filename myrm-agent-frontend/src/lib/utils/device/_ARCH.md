# lib/utils/device/

设备检测域子包：移动端与触控设备判定。**无** React 组件，全部纯函数，零外部依赖。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/device`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

- `index.ts`：域门面 barrel — 显式导出清单聚合两文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `deviceDetection.ts`：设备检测 — checkIsMobile 环境侧移动端判定。
- `deviceUtils.ts`：设备工具 — isMobileDevice / isTouchDevice 特征查询级设备判定。

## 依赖

- 零外部依赖（纯检测函数）。
