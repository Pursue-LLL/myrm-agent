from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class IMUser(BaseModel):
    name: str
    open_id: str
    department: str
    avatar_url: str


class IMSearchResponse(BaseModel):
    users: list[IMUser]


@router.get("/im/users/search", response_model=IMSearchResponse)
async def search_im_users(
    query: str = Query(..., description="Name to search for"),
    provider: str = Query("feishu", description="feishu or dingtalk"),
) -> IMSearchResponse:
    """Lightweight search users API for IM group management.

    In a real environment, this would call Feishu/DingTalk search APIs
    with the enterprise access token. For demonstration/testing, it returns mocked results.
    """
    query = query.lower()

    # Mock database
    mock_db = [
        {
            "name": "张伟",
            "open_id": "ou_zw_001",
            "department": "研发部",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=zw1",
        },
        {
            "name": "张伟",
            "open_id": "ou_zw_002",
            "department": "销售部",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=zw2",
        },
        {
            "name": "张伟",
            "open_id": "ou_zw_003",
            "department": "法务部",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=zw3",
        },
        {
            "name": "小李",
            "open_id": "ou_xl_001",
            "department": "产品部",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=xl1",
        },
        {
            "name": "赵总",
            "open_id": "ou_zz_001",
            "department": "高管团队",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=zz1",
        },
        {
            "name": "王总",
            "open_id": "ou_wz_001",
            "department": "研发部",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=wz1",
        },
        {
            "name": "李律",
            "open_id": "ou_ll_001",
            "department": "法务部",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=ll1",
        },
        {
            "name": "老王",
            "open_id": "ou_lw_001",
            "department": "后端研发",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=lw1",
        },
        {
            "name": "小赵",
            "open_id": "ou_xz_001",
            "department": "DBA",
            "avatar_url": "https://api.dicebear.com/7.x/avataaars/svg?seed=xz1",
        },
    ]

    results = [IMUser(**user) for user in mock_db if query in user["name"].lower()]
    return IMSearchResponse(users=results)
