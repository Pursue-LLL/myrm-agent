"""Sandbox 平台实现

沙箱模式的服务实现，由控制平面管理的隔离运行环境。

核心理念：
- 容器化执行：由外部控制服务管理沙箱生命周期
- 完整身份：由控制平面注入单租户身份
- 本地存储：数据落在控制平面挂载的 Volume，文件服务直接使用 app/core/storage/service.py

组件：
- entitlements: 控制平面配额与 Work Unit 预算客户端
- tool_gateway: 沙箱 tool gateway 凭据解析
- saas_providers_seed: SaaS 首启模型配置种子
"""
