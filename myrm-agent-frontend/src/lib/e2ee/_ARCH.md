# e2ee/

## 架构概述

端到端加密(E2EE)客户端逻辑层。提供 NaCl Box 密钥交换、会话管理、指纹计算和状态 Hook。

## 文件清单

| 文件               | 职责                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------- |
| `client.ts`                               | E2EE 核心：密钥对生成、握手协商、会话存储（sessionStorage）、加解密函数、base64 编解码 |
| `fingerprint.ts`                          | 公钥指纹计算纯函数（SHA-512 via `nacl.hash`），支持 raw bytes 和 base64 输入           |
| `useE2EEStatus.ts`                        | React Hook：封装 E2EE 握手状态、指纹、算法、会话 ID，供 UI 组件消费                    |
| `offlineE2EECryptoBridge.ts`              | 移动离线端到端信封加解密桥：基于 Web Crypto API (SubtleCrypto)，采用 AES-GCM-256 + PBKDF2 (100,000 次 SHA-256 哈希迭代) 实现客户端零知识信封加密与本地设备根密钥管理 |
| `__tests__/offlineE2EECryptoBridge.test.ts` | 单元测试：覆盖信封加解密数据完整性、自定义口令隔离性、派生密钥确定性与设备根凭据生成机制 |

## 依赖

- `tweetnacl` — NaCl 密码学原语
- `@/lib/mobileRemote` — `ensureMobileE2EE` 握手入口
