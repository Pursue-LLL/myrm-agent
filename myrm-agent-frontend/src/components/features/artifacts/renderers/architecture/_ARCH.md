# architecture/

交互式架构拓扑图、因果依赖追踪与演进 Diff 渲染模块。

## 架构概述

基于 React Flow (`@xyflow/react`) 和 Dagre (`@dagrejs/dagre`) 构建的纯前端轻量级拓扑图谱渲染系统。通过标准化 JSON IR 解析系统架构元数据，提供层次分明、动静结合的节点调用关系视图、两点间 BFS 最短有向路径探查、单节点因果全景依赖遍历与多版本演进 Diff 语义对比。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `ArchitecturePreview.tsx` | 核心 | 架构图主预览容器，集成缩放、搜索过滤、Diff 切换、SVG/PNG 导出与 JSON 复制交互 | ✅ |
| `ArchitectureCustomNode.tsx` | 核心 | 定制化 React Flow 节点组件，支持 9 种技术组件形态、健康度状态徽章与 Diff 高亮边框 | ✅ |
| `layout.ts` | 核心 | Dagre 分层自动排版计算引擎、IR 防御性自愈与两点间 BFS 最短有向路径算法实现 | ✅ |
| `diff.ts` | 核心 | 架构快照间语义级对比算法，计算增删改节点及调用关系，生成 DiffSummary 量化指标 | ✅ |
| `types.ts` | 核心 | Architecture IR 标准拓扑数据协议接口与类型定义（NodeIR, EdgeIR, DiffSummary） | ✅ |
| `__tests__/architectureLogic.test.ts` | 辅助 | 排版计算、IR 净化、Diff 判定与双节点最短路径算法的自动化回归单测 | ✅ |
