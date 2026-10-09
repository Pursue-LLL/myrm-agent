# [POS]: tests/api/memory/test_procedure_experience_api.py
# [INPUT]: app.api.memory.procedure_experience_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite (Item 104)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.procedure_experience_router import router as procedure_experience_router
from app.services.memory.procedure_experience_service import (
    ProcedureExperienceService,
    get_procedure_experience_service,
)


@pytest.fixture
def isolated_service() -> ProcedureExperienceService:
    """Provides an isolated ProcedureExperienceService instance."""
    return ProcedureExperienceService()


@pytest.fixture
def test_app(isolated_service: ProcedureExperienceService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(procedure_experience_router, prefix="/api/memory")
    app.dependency_overrides[get_procedure_experience_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_procedure_register_and_list_api(test_app: FastAPI) -> None:
    """Validate registering, listing, and retrieving 8-field procedure memories."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a valid 8-field procedure entry
        valid_payload = {
            "name": "多租户缓存防击穿更新",
            "operation_intent": "在更新高并发热点缓存前获取分布式互斥锁并预热旁路缓存",
            "preconditions": ["Redis 集群处于健康可用状态", "互斥锁具备租期续约保护机制"],
            "immutable_boundary": ["严禁无锁并发读写穿透到底层关系数据库"],
            "procedure_steps": [
                "1. 获取 key 粒度分布式互斥锁",
                "2. 查询数据库最新值",
                "3. 回写缓存并设置随机 TTL",
                "4. 释放互斥锁",
            ],
            "write_field_provenance": {
                "cache_ttl": "基于基础 TTL 叠加 10% 随机偏移",
                "lock_token": "由客户端实例标识与纳秒时间戳拼接",
            },
            "anti_patterns": [
                "直接覆盖写入缓存但不设置 TTL",
                "捕获异常后未在 finally 块中释放锁",
            ],
            "applicability": ["高频热点用户资料与商品详情缓存更新"],
            "negative_applicability": ["本地单机无并发低频配置读取场景"],
            "confidence": 1.0,
        }

        res_reg = await client.post("/api/memory/procedure/register", json=valid_payload)
        assert res_reg.status_code == 200
        data_reg = res_reg.json()
        assert "retrieval_anchor" in data_reg
        assert "proc_" in data_reg["entry_id"]
        entry_id = data_reg["entry_id"]

        # 2. Get registered entry by ID
        res_get = await client.get(f"/api/memory/procedure/{entry_id}")
        assert res_get.status_code == 200
        assert res_get.json()["name"] == "多租户缓存防击穿更新"

        # 3. List all registered procedures (seeds + new entry)
        res_list = await client.get("/api/memory/procedure/list")
        assert res_list.status_code == 200
        entries = res_list.json()
        assert len(entries) >= 3

        # 4. Attempt to register an invalid payload missing preconditions (should 400)
        invalid_payload = {
            "name": "缺少前置条件的空条目",
            "operation_intent": "测试协议校验拦截",
            "preconditions": [],
            "immutable_boundary": ["不可变边界"],
            "procedure_steps": ["步骤1"],
            "write_field_provenance": {"field": "source"},
            "anti_patterns": ["反模式"],
            "applicability": ["适用环境"],
            "negative_applicability": ["不适用环境"],
        }
        res_invalid = await client.post("/api/memory/procedure/register", json=invalid_payload)
        assert res_invalid.status_code in (400, 422)


@pytest.mark.asyncio
async def test_procedure_dual_node_retrieval_and_split_api(test_app: FastAPI) -> None:
    """Validate fixed-count dual-node retrieval and multi-intent trace decomposition."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. First-user intent node retrieval (fixed top_n=2)
        q_first_user = {
            "query_text": "在主分支发布应用并做门禁检查",
            "node_kind": "first_user",
            "top_n": 2,
        }
        res_fu = await client.post("/api/memory/procedure/retrieve", json=q_first_user)
        assert res_fu.status_code == 200
        data_fu = res_fu.json()
        assert data_fu["node_kind"] == "first_user"
        assert len(data_fu["matched_entries"]) <= 2
        assert any("发布" in e["name"] for e in data_fu["matched_entries"])

        # 2. Pre-write intercept node retrieval (fixed top_n=1)
        q_pre_write = {
            "query_text": "在写数据库前进行租户隔离检查",
            "node_kind": "pre_write",
            "top_n": 1,
        }
        res_pw = await client.post("/api/memory/procedure/retrieve", json=q_pre_write)
        assert res_pw.status_code == 200
        data_pw = res_pw.json()
        assert data_pw["node_kind"] == "pre_write"
        assert len(data_pw["matched_entries"]) == 1
        assert "隔离" in data_pw["matched_entries"][0]["name"]

        # 3. Multi-intent decomposition test
        raw_trace = """
Intent 1: 检查代码仓库依赖冲突并更新 package.json
先运行 bun outdated，然后对比锁定版本，最后更新依赖。
Intent 2: 构建生产包并部署到测试集群
先运行 bun run build，然后生成 Docker 镜像并推送到镜像仓库。
"""
        split_res = await client.post("/api/memory/procedure/split-intents", json={"raw_text": raw_trace})
        assert split_res.status_code == 200
        split_data = split_res.json()
        assert split_data["fragment_count"] == 2
        assert len(split_data["fragments"]) == 2
