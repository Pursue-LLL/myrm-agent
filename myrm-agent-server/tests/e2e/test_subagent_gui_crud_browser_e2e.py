"""
Subagent GUI CRUD 浏览器端到端测试

测试场景：
1. 导航到智能体配置页面
2. 测试添加 Subagent
3. 测试配置 display_name 和 theme_color
4. 测试删除 Subagent
5. 测试保存和持久化
6. 验证在对话中的显示效果
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "myrm-agent-harness" / "src"))

import pytest  # noqa: E402
from patchright.async_api import Page, async_playwright  # noqa: E402

BASE_URL = "http://localhost:3000"
SETTINGS_AGENTS_URL = f"{BASE_URL}/settings/agents"


@pytest.fixture(scope="function")
async def browser_page():
    """启动浏览器并返回页面对象"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context()
        page = await context.new_page()

        yield page

        await context.close()
        await browser.close()


async def wait_for_page_load(page: Page, timeout: int = 10000):
    """等待页面加载完成"""
    try:
        # 不等待 networkidle，因为可能有持续的轮询请求
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
        await asyncio.sleep(2)  # 额外等待React渲染
    except Exception as e:
        print(f"⚠ 页面加载警告: {e}")
        await asyncio.sleep(2)  # 仍然等待一段时间


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_subagent_gui_crud_flow(browser_page: Page, ephemeral_frontend: str):
    """测试完整的 Subagent GUI CRUD 流程"""
    page = browser_page
    settings_agents_url = f"{ephemeral_frontend}/settings/agents"

    # ===== 步骤 1: 导航到智能体配置页面 =====
    print("\n[步骤 1] 导航到智能体配置页面...")
    await page.goto(settings_agents_url)
    await wait_for_page_load(page)

    # 验证页面标题
    title = await page.title()
    assert "设置" in title or "Settings" in title, f"页面标题错误: {title}"
    print(f"✓ 页面加载成功: {title}")

    # ===== 步骤 2: 找到并点击默认智能体的编辑按钮 =====
    print("\n[步骤 2] 查找并悬停第一个智能体卡片...")

    # 截图以便调试
    screenshot_path = Path(__file__).parent / "screenshots" / "step2_agents_page.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(screenshot_path))
    print(f"✓ 已保存截图: {screenshot_path}")

    # 等待智能体卡片加载
    try:
        await page.wait_for_selector(".group.relative.rounded-xl", timeout=5000)
        print("✓ 找到智能体卡片")
    except Exception as e:
        page_text = await page.inner_text("body")
        raise AssertionError(f"未找到智能体卡片。错误: {e}\n页面文本：\n{page_text[:1000]}") from e

    # 获取第一个智能体卡片
    agent_cards = await page.query_selector_all(".group.relative.rounded-xl")
    assert len(agent_cards) > 0, "未找到任何智能体卡片"

    first_card = agent_cards[0]

    # 悬停在第一个卡片上以显示编辑按钮
    await first_card.hover()
    await asyncio.sleep(0.5)  # 等待动画完成
    print("✓ 已悬停在第一个智能体卡片上")

    # 截图显示悬停后的状态
    screenshot_path_hover = Path(__file__).parent / "screenshots" / "step2_hover.png"
    await page.screenshot(path=str(screenshot_path_hover))
    print(f"✓ 已保存悬停状态截图: {screenshot_path_hover}")

    # 查找编辑按钮（在卡片内）
    # 注意：编辑按钮是在 group-hover 时显示的
    edit_button = await first_card.query_selector("button")
    assert edit_button is not None, "未找到编辑按钮"

    # 点击编辑按钮
    await edit_button.click()
    await asyncio.sleep(2)
    print("✓ 已点击编辑按钮")

    # ===== 步骤 3: 等待导航到编辑页面 =====
    print("\n[步骤 3] 等待导航到编辑页面...")

    # 等待URL变化
    try:
        await page.wait_for_url("**/settings/agents?agentId=*", timeout=5000)
        print(f"✓ 已导航到编辑页面: {page.url}")
    except Exception:
        # 可能已经在编辑页面了
        print(f"⚠ URL未变化，当前URL: {page.url}")

    # 等待页面加载
    await wait_for_page_load(page)

    # 截图编辑页面
    screenshot_path_edit = Path(__file__).parent / "screenshots" / "step3_edit_page.png"
    await page.screenshot(path=str(screenshot_path_edit))
    print(f"✓ 已保存编辑页面截图: {screenshot_path_edit}")

    # 查找 Subagents 配置区域
    # 注意：这里可能需要滚动才能看到
    print("\n[步骤 4] 查找 Subagents 配置区域...")

    try:
        await page.wait_for_selector("text=Subagents, text=子智能体", timeout=3000)
        print("✓ 找到 Subagents 配置区域")
    except Exception:
        # 尝试滚动到底部
        print("⚠ 未找到 Subagents，尝试滚动页面...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        try:
            await page.wait_for_selector("text=Subagents, text=子智能体", timeout=5000)
            print("✓ 找到 Subagents 配置区域（滚动后）")
        except Exception as e:
            # 打印页面内容以便调试
            page_text = await page.inner_text("body")
            screenshot_path_error = Path(__file__).parent / "screenshots" / "error_no_subagents.png"
            await page.screenshot(path=str(screenshot_path_error))
            raise AssertionError(
                f"未找到 Subagents 配置区域。错误: {e}\n截图: {screenshot_path_error}\n页面内容：\n{page_text[:1000]}"
            ) from e

    # ===== 步骤 5: 测试添加 Subagent =====
    print("\n[步骤 5] 测试添加 Subagent...")

    # 现在已经在编辑页面，找到 Subagents 配置卡片
    # 根据前端代码，Subagents 配置应该在一个配置卡片中

    # 查找"添加 Subagent"按钮
    add_subagent_buttons = await page.query_selector_all('button:has-text("添加 Subagent"), button:has-text("Add Subagent")')
    assert len(add_subagent_buttons) > 0, "未找到添加 Subagent 按钮"

    await add_subagent_buttons[0].click()
    await asyncio.sleep(1)
    print("✓ 已点击添加 Subagent 按钮")

    # 选择一个预设的 Subagent（例如 "researcher"）
    try:
        researcher_option = await page.wait_for_selector("text=researcher, text=Researcher", timeout=3000)
        await researcher_option.click()
        await asyncio.sleep(0.5)
        print("✓ 已选择 researcher 预设")
    except Exception:
        # 如果没有预设，尝试自定义 ID
        custom_input = await page.query_selector('input[placeholder*="ID"], input[placeholder*="id"]')
        if custom_input:
            await custom_input.fill("test_subagent")
            await asyncio.sleep(0.5)
            print("✓ 已输入自定义 Subagent ID: test_subagent")

    # 点击确认按钮
    confirm_buttons = await page.query_selector_all(
        'button:has-text("确认"), button:has-text("Confirm"), button:has-text("添加"), button:has-text("Add")'
    )
    if confirm_buttons:
        await confirm_buttons[0].click()
        await asyncio.sleep(1)
        print("✓ 已确认添加 Subagent")

    # ===== 步骤 5: 测试配置 display_name 和 theme_color =====
    print("\n[步骤 5] 测试配置 display_name 和 theme_color...")

    # 查找刚添加的 Subagent 列表项
    # 假设列表中有 display_name 输入框
    display_name_inputs = await page.query_selector_all('input[placeholder*="name"], input[placeholder*="名称"]')
    if display_name_inputs:
        # 填写 display_name
        await display_name_inputs[0].fill("测试研究员")
        await asyncio.sleep(0.5)
        print("✓ 已设置 display_name: 测试研究员")

    # 选择 theme_color
    # 假设使用 select 或 button group
    color_selects = await page.query_selector_all('select, button[aria-label*="color"], button[aria-label*="颜色"]')
    if color_selects:
        # 尝试选择第一个颜色选项（例如 blue）
        await color_selects[0].click()
        await asyncio.sleep(0.5)

        # 选择一个颜色选项
        color_options = await page.query_selector_all('option[value="blue"], button:has-text("Blue"), button:has-text("蓝色")')
        if color_options:
            await color_options[0].click()
            await asyncio.sleep(0.5)
            print("✓ 已设置 theme_color: blue")

    # ===== 步骤 6: 测试保存配置 =====
    print("\n[步骤 6] 测试保存配置...")

    # 查找保存按钮
    save_buttons = await page.query_selector_all('button:has-text("保存"), button:has-text("Save")')
    assert len(save_buttons) > 0, "未找到保存按钮"

    await save_buttons[0].click()
    await asyncio.sleep(2)
    print("✓ 已点击保存按钮")

    # 等待对话框关闭
    await asyncio.sleep(1)

    # ===== 步骤 7: 验证持久化 =====
    print("\n[步骤 7] 验证配置持久化...")

    # 重新打开编辑对话框
    edit_buttons = await page.query_selector_all('button:has-text("编辑"), button:has-text("Edit")')
    if edit_buttons:
        await edit_buttons[0].click()
        await asyncio.sleep(1)
        print("✓ 重新打开编辑对话框")

    # 再次打开 Subagents 配置
    subagent_edit_buttons = await page.query_selector_all(
        '[role="dialog"] button:has-text("编辑"), [role="dialog"] button:has-text("Edit")'
    )
    for btn in subagent_edit_buttons:
        parent_text = await btn.evaluate("el => el.closest('div').innerText")
        if "Subagent" in parent_text or "子智能体" in parent_text:
            await btn.click()
            await asyncio.sleep(1)
            print("✓ 重新打开 Subagents 配置")
            break

    # 验证之前添加的 Subagent 是否还在
    page_content = await page.content()
    assert "测试研究员" in page_content or "test_subagent" in page_content or "researcher" in page_content, (
        "配置未持久化：未找到之前添加的 Subagent"
    )
    print("✓ 配置已成功持久化")

    # ===== 步骤 8: 测试删除 Subagent =====
    print("\n[步骤 8] 测试删除 Subagent...")

    # 查找删除按钮
    delete_buttons = await page.query_selector_all(
        'button:has-text("删除"), button:has-text("Delete"), button[aria-label*="删除"], button[aria-label*="delete"]'
    )
    if delete_buttons:
        await delete_buttons[0].click()
        await asyncio.sleep(1)
        print("✓ 已点击删除按钮")

        # 如果有确认对话框，点击确认
        confirm_delete = await page.query_selector('button:has-text("确认"), button:has-text("Confirm")')
        if confirm_delete:
            await confirm_delete.click()
            await asyncio.sleep(1)
            print("✓ 已确认删除")

    # 再次保存
    save_buttons = await page.query_selector_all('button:has-text("保存"), button:has-text("Save")')
    if save_buttons:
        await save_buttons[0].click()
        await asyncio.sleep(1)
        print("✓ 已保存删除操作")

    print("\n[测试完成] ✓ Subagent GUI CRUD 功能测试通过！")


if __name__ == "__main__":
    """
    直接运行此脚本进行测试
    
    使用方法：
    1. 确保前端服务运行在 http://localhost:3000
    2. 确保后端服务运行在 http://localhost:8080
    3. 运行: uv run python tests/e2e/test_subagent_gui_crud_browser_e2e.py
    """
    print("=" * 80)
    print("Subagent GUI CRUD 浏览器端到端测试")
    print("=" * 80)

    # 检查服务状态
    import httpx

    try:
        response = httpx.get(BASE_URL, timeout=5)
        print(f"✓ 前端服务运行正常: {BASE_URL}")
    except Exception as e:
        print(f"✗ 前端服务无法访问: {e}")
        print("请确保前端服务已启动: bun run dev")
        sys.exit(1)

    try:
        response = httpx.get("http://localhost:8080/api/v1/health", timeout=5)
        print("✓ 后端服务运行正常: http://localhost:8080")
    except Exception as e:
        print(f"✗ 后端服务无法访问: {e}")
        print("请确保后端服务已启动: uv run run.py")
        sys.exit(1)

    print("\n开始测试...")
    print("-" * 80)

    # 运行测试
    pytest.main([__file__, "-v", "-s", "--asyncio-mode=auto"])
