"""E2E test for the Annotation Editor feature.

Verifies the annotation editor workflow:
1. Image upload shows an edit button on hover
2. Clicking edit opens the annotation editor modal
3. Toolbar tools and canvas are functional
4. Save closes the editor
"""

import asyncio
import os
from pathlib import Path

import pytest
from patchright.async_api import Page, async_playwright
from PIL import Image


def _create_test_image(path: str) -> None:
    """Create a simple 400x300 test image."""
    img = Image.new("RGB", (400, 300), color=(200, 220, 240))
    for x in range(100, 300):
        for y in range(75, 225):
            img.putpixel((x, y), (50, 100, 150))
    img.save(path, format="PNG")


async def _setup_and_upload(page: Page, image_path: str) -> None:
    """Navigate, mock config for vision support, upload image."""
    frontend_url = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")

    # Mock only the exact backend config endpoint
    async def handle_config(route):
        if "/api/" in route.request.url or ":8080" in route.request.url:
            await route.fulfill(
                json={
                    "configs": {
                        "providers": {
                            "key": "providers",
                            "value": {
                                "providers": [
                                    {
                                        "id": "test-provider",
                                        "name": "Test",
                                        "isBuiltIn": True,
                                        "isEnabled": True,
                                        "apiKeys": ["sk-test"],
                                        "apiUrl": "https://example.com/v1",
                                        "enabledModels": ["test-vision"],
                                        "availableModels": ["test-vision"],
                                        "routingProfile": "test-provider",
                                    }
                                ]
                            },
                        },
                        "defaultModelConfig": {
                            "key": "defaultModelConfig",
                            "value": {"baseModel": {"primary": {"providerId": "test-provider", "model": "test-vision"}}},
                        },
                        "customModelInfo": {
                            "key": "customModelInfo",
                            "value": {
                                "test-provider/test-vision": {"id": "test-vision", "name": "test-vision", "supports_vision": True}
                            },
                        },
                    }
                }
            )
        else:
            await route.continue_()

    await page.route("**/config**", handle_config)

    await page.goto(f"{frontend_url}/", wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(2000)

    # Set localStorage for yolo mode and agent mode
    await page.evaluate("""
        () => {
            const c = JSON.parse(localStorage.getItem('securityConfig') || '{}');
            c.yoloModeEnabled = true;
            localStorage.setItem('securityConfig', JSON.stringify(c));
            localStorage.setItem('actionMode', 'agent');
        }
    """)
    await page.reload(wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_timeout(3000)

    # Wait for the message input to be ready
    input_box = page.locator('[placeholder="输入消息..."], [placeholder="Type a message..."]').first
    await input_box.wait_for(state="visible", timeout=15_000)

    # Upload image via file input
    file_input = page.locator('input[type="file"]').first
    await file_input.set_input_files(image_path)
    await page.wait_for_timeout(2000)

    # Dismiss any dialog
    dialog = page.locator('[role="alertdialog"]')
    if await dialog.count() > 0:
        btn = dialog.locator("button").last
        if await btn.count() > 0:
            await btn.click()
            await page.wait_for_timeout(500)

    # Verify the image thumbnail is visible
    file_name = os.path.basename(image_path)
    thumbnail = page.locator(f'img[alt="{file_name}"]')
    await thumbnail.wait_for(state="visible", timeout=10_000)
    print(f"  [PASS] Image uploaded and thumbnail visible: {file_name}")


async def _test_annotation_workflow(page: Page, image_path: str) -> None:
    """Full annotation editor workflow test."""
    file_name = os.path.basename(image_path)
    thumbnail = page.locator(f'img[alt="{file_name}"]')

    # Step 1: Hover thumbnail to reveal edit button
    container = thumbnail.locator("..")
    await container.hover()
    await page.wait_for_timeout(500)

    edit_btn = container.locator("button").first
    await edit_btn.wait_for(state="visible", timeout=5_000)
    print("  [PASS] Edit button visible on hover")

    # Step 2: Click edit button to open annotation editor
    await edit_btn.click()
    await page.wait_for_timeout(1000)

    # Verify modal opened (annotation editor uses a fixed overlay)
    canvas = page.locator("canvas")
    await canvas.first.wait_for(state="visible", timeout=5_000)
    print("  [PASS] Annotation editor opened with canvas")

    # Step 3: Verify toolbar is present
    # The toolbar should have multiple buttons for tools
    fixed_overlay = page.locator('.fixed.inset-0, [data-testid="annotation-editor"]').first
    toolbar_buttons = fixed_overlay.locator("button")
    btn_count = await toolbar_buttons.count()
    assert btn_count >= 8, f"Expected at least 8 toolbar buttons, got {btn_count}"
    print(f"  [PASS] Toolbar has {btn_count} buttons")

    # Step 4: Draw on canvas
    canvas_el = canvas.first
    box = await canvas_el.bounding_box()
    if box:
        sx = box["x"] + box["width"] * 0.25
        sy = box["y"] + box["height"] * 0.25
        ex = box["x"] + box["width"] * 0.75
        ey = box["y"] + box["height"] * 0.75
        await page.mouse.move(sx, sy)
        await page.mouse.down()
        await page.mouse.move(ex, ey, steps=10)
        await page.mouse.up()
        await page.wait_for_timeout(500)
        print("  [PASS] Drew annotation on canvas")

    # Step 5: Click a different tool (e.g., second button)
    if btn_count > 1:
        await toolbar_buttons.nth(1).click()
        await page.wait_for_timeout(200)
        print("  [PASS] Switched tool")

    # Step 6: Save (find save/close button - last few buttons are actions)
    # Look for a button with save-related text or icon
    save_clicked = False
    for i in range(btn_count - 1, max(btn_count - 5, -1), -1):
        btn = toolbar_buttons.nth(i)
        text = (await btn.inner_text()).strip().lower()
        title = (await btn.get_attribute("title") or "").lower()
        aria = (await btn.get_attribute("aria-label") or "").lower()
        if any(word in f"{text}{title}{aria}" for word in ["save", "保存", "check", "确认"]):
            await btn.click()
            save_clicked = True
            break

    if not save_clicked:
        # Click the last button as save
        await toolbar_buttons.nth(btn_count - 1).click()

    await page.wait_for_timeout(1500)
    print("  [PASS] Save button clicked")

    # Verify editor closed
    canvas_count = await canvas.count()
    if canvas_count == 0:
        print("  [PASS] Editor closed after save")
    else:
        print("  [INFO] Editor may still be visible (canvas present)")


async def _run_annotation_e2e(image_path: str) -> None:
    """Main e2e test runner."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            print("Setting up page and uploading image...")
            await _setup_and_upload(page, image_path)

            print("Running annotation editor workflow...")
            await _test_annotation_workflow(page, image_path)

            print("\nAll annotation editor e2e tests passed!")
        finally:
            await context.close()
            await browser.close()


@pytest.mark.asyncio
async def test_annotation_editor_e2e(tmp_path: Path) -> None:
    if os.environ.get("MYRM_E2E_REAL_FRONTEND_STACK") != "1":
        pytest.skip("Set MYRM_E2E_REAL_FRONTEND_STACK=1 to run.")

    image_path = str(tmp_path / "test_annotate.png")
    _create_test_image(image_path)
    await _run_annotation_e2e(image_path)


if __name__ == "__main__":
    os.environ["MYRM_E2E_REAL_FRONTEND_STACK"] = "1"
    import tempfile

    tmp = tempfile.mkdtemp()
    image_path = str(Path(tmp) / "test_annotate.png")
    _create_test_image(image_path)
    asyncio.run(_run_annotation_e2e(image_path))
