-- Apache AGE 初始化脚本
-- 在 PostgreSQL 数据库中安装和配置 AGE 扩展

-- 创建 AGE 扩展
CREATE EXTENSION IF NOT EXISTS age;

-- 加载 AGE
LOAD 'age';

-- 设置搜索路径（包含 AGE 的 ag_catalog schema）
ALTER DATABASE myrmagent SET search_path = ag_catalog, "$user", public;

-- 创建图（用于情景记忆）
SELECT create_graph('episodic_memory');

-- 输出成功信息
DO $$
BEGIN
    RAISE NOTICE '✅ Apache AGE initialized successfully';
    RAISE NOTICE '   - Extension: age';
    RAISE NOTICE '   - Graph: episodic_memory';
    RAISE NOTICE '   - Search path: ag_catalog, "$user", public';
END $$;
