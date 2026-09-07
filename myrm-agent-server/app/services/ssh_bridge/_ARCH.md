# app/services/ssh_bridge/

## 架构概述
多主机 SSH 远程运维资产管理、OpenSSH (`~/.ssh/config`) 配置导入解析、SFTP 目录文件传输与 Agent 资产安全别名直连桥接模块。

## 文件与子模块索引

| 文件 | 角色 | 职责描述 | I/O/P |
|------|------|----------|-------|
| `__init__.py` | 包声明 | 导出模型、解析器、管理器与执行引擎。 | ✅ |
| `models.py` | 数据模型 | 包含 `SSHHostAsset`、`SSHConfigParsedHost`、`SSHCommandResult`、`SFTPTransferResult` 等强类型。 | ✅ |
| `parser.py` | 解析器 | `OpenSSHConfigParser`，负责解析 OpenSSH 配置文件中各 Host 区块、端口、私钥与跳板机配置。 | ✅ |
| `manager.py` | 资产管理 | `SSHAssetManager`，负责资产增删改查、别名冲突校验、标签过滤与配置批量导入。 | ✅ |
| `executor.py` | 桥接执行器 | `SSHBridgeExecutor` 与 `SFTPBridgeEngine`，提供安全别名执行、高危命令防护、超时控制与 SFTP 校验。 | ✅ |
