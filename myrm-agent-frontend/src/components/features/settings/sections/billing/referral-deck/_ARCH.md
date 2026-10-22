# Referral Fission Deck & Zero-Dox Privacy Architecture

## 1. 业务目标与背景
针对 Nous Portal 等竞品直接在推荐链接中暴露用户真实全名或邮箱前缀（如 `portal.nousresearch.com/r/john-smith`）导致推特与社交媒体分享时产生严重人肉开盒（Doxxing）与隐私泄露的痛点：
- **Zero-Dox 隐私红线**：
  - 默认基于 CSPRNG 加密安全伪随机数生成 6~8 位无语义短码（如 `myrmagent.ai/r/k7m9xp`）；
  - 提供个性化伪名（Pseudonymous Slug）修改器，内置实时 PII 敏感词与邮箱/手机号特征阻断算法，杜绝开盒风险。
- **双向算力飞轮与透明账本**：
  - 受邀伙伴注册立享 $15 美元云端算力礼包（抵扣高性能沙箱与模型调用成本）；
  - 邀请人获赠 $10 算力赠金 + 10% 云端沙箱包月持续返佣（Cloud Kickback）；
  - 与智能体模板分享链接自动编织（`?ref=` 参数），实现内容资产与商业裂变协同。
- **防刷反作弊风控门禁 (Anti-Sybil Gate)**：
  - 浏览器 Canvas 熵、设备指纹及 IP 子网综合审计，杜绝小号脚本套利。

## 2. 模块契约与组件职责
- `referralDeckTypes.ts`：定义推荐 Profile、双向算力账本 `CreditLedger`、收益流水记录 `ReferralEarningRecord` 与风控审计 `FraudRiskAudit`。
- `useReferralFissionStore.ts`：纯逻辑核心与状态机，提供 `generateCsprngRandomSlug`、`validateZeroDoxSlug` 校验算法、以及 `weaveReferralIntoTemplateUrl` 模板编织能力。
- `ReferralFissionDeck.tsx`：裂变中枢看板主组件，呈现专属短链、伪名修改器、算力仪表盘、风控卡片与收益流水。
- `ReferralShareCardPreview.tsx`：受邀者端优惠与社交分享海报卡片预览。

## 3. 质量与安全约束
- 原生语义化结构与严格 a11y，零原生 emoji，统一采用 Lucide 矢量图标。
- 单文件行数均受控在 270 行以内（远低于 400 行上限）。
- 零 `any`，全面 TypeScript 静态类型推导。
