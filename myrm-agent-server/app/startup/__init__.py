"""
@input: 无外部依赖，纯启动基础设施
@output: 对外提供启动阶段各子模块（env_loader, config_check, health_check, server_lock, runners）
@pos: 应用启动编排模块 —— 环境加载、配置校验、进程锁、服务器启动

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""
