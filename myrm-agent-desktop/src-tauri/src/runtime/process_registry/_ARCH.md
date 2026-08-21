# process_registry 模块架构

[INPUT]
- `crate::utils::process_tree` (POS: 跨平台进程树安全销毁与 Windows Job Object 管理器)

[OUTPUT]
- `ProcessRegistry`: 全局受管进程注册中心
- `ManagedProcessEntry`: 进程元数据条目
- `ProcessRole`: 进程角色类型
- `ProcessStatus`: 进程生命周期状态

[POS]
`src-tauri/src/runtime/process_registry/` 桌面端受管进程注册中心与生命周期管理模块根。

---

## 架构概览

提供桌面端所有 Sidecar 进程及动态 Agent Session 子进程的集中生命周期追踪、退出状态捕获与定向进程树销毁。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 模块导出 | ✅ |
| `types.rs` | 核心 | 进程角色、状态机与条目数据结构 | ✅ |
| `registry.rs` | 核心 | 并发安全注册表实现（启动登记、崩溃捕获、有界历史缓存、定向整树销毁） | ✅ |
