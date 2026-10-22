# specialty-suites-gateway/

## 架构概述

本模块实现桌面端统一专业套件侧栏工作台与移动端免配置扫码热插拔伴侣网关（Unified Workplace Hub & Zero-Config Mobile Companion Gateway）。
彻底解决多端入口割裂、Web 与客户端功能不一致且定时任务不同步、以及移动端接入配置繁琐门槛高的痛点。
提供专家智能体套件（财务/法务/数据/工程）、企业连接器（飞书/企微/钉钉/Telegram）、统一定时任务中心（云端常驻与本地自动分流）、以及 1 秒扫码即连的 Ed25519 加密移动伴侣通道。对标千问多端制作台与 WorkBuddy/豆包远程助理精髓并超越。

## 文件组织

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `specialtyGatewayTypes.ts` | Types | 核心数据模型契约（SpecialtySuiteItem, EnterpriseConnector, ScheduledJobSummary, MobilePairingSession, CompanionSyncStatus） | [INPUT] 无外部运行时依赖<br>[OUTPUT] 导出数据类型与枚举<br>[POS] 统一类型契约事实源 |
| `useMobilePairingQrGateway.ts` | Hook | 动态加密二维码生成、倒计时生命周期与端到端握手 Hook | [INPUT] specialtyGatewayTypes<br>[OUTPUT] 配对会话状态与生命周期控制器<br>[POS] 扫码配对核心业务逻辑 |
| `ZeroConfigMobilePairingModal.tsx` | UI | 免配置扫码配对弹窗（渠道切换、二维码展示、临时密钥与已绑定伴侣卡片） | [INPUT] useMobilePairingQrGateway, specialtyGatewayTypes<br>[OUTPUT] 语义化配对模态框<br>[POS] 跨端配对交互界面 |
| `UnifiedSpecialtyWorkplaceHub.tsx` | Core | 桌面端/Web 统一专业套件侧栏工作台（套件、连接器、统一定时中心集成） | [INPUT] specialtyGatewayTypes, ZeroConfigMobilePairingModal<br>[OUTPUT] 侧边栏工作台主表面<br>[POS] 专业套件与中枢总览视图 |
| `index.ts` | Facade | 门面统一导出 | [INPUT] 模块内部所有导出<br>[OUTPUT] 统一向外部提供公共 API<br>[POS] 模块对外唯一门面 |
