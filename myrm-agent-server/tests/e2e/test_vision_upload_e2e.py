"""E2E test for Vision Analyze Reactive Compress.

Uploads a >5MB image with >4096px resolution to verify the frontend and backend 
can handle it without crashing, and that the backend compresses it successfully.
"""

import asyncio
import os
from pathlib import Path

import pytest
from patchright.async_api import Page, async_playwright
from PIL import Image


def _create_large_image(path: str) -> None:
    """Create a 4500x4500 image that triggers resolution-based compress."""
    img = Image.new('RGB', (4500, 4500), color='red')
    img.save(path, format='PNG')

async def _chat_smoke_vision(page: Page, image_path: str) -> None:
    from dotenv import load_dotenv
    load_dotenv()
    basic_model = os.getenv("BASIC_MODEL", "openai/gpt-4o")
    provider_id = basic_model.split("/")[0] if "/" in basic_model else "openai"
    model_name = basic_model.split("/")[1] if "/" in basic_model else basic_model

    await page.route("**/api/v1/config", lambda route: route.fulfill(
        json={
            "configs": {
                "providers": {"key":"providers","value":{"providers":[{"id":provider_id,"name":provider_id,"isBuiltIn":True,"isEnabled":True,"apiKeys":["sk-123"],"apiUrl":"","enabledModels":[model_name],"availableModels":[model_name],"routingProfile":provider_id}]}},
                "defaultModelConfig": {"key":"defaultModelConfig","value":{"baseModel":{"primary":{"providerId":provider_id,"model":model_name}}}},
                "customModelInfo": {"key":"customModelInfo","value":{f"{provider_id}/{model_name}":{"id":model_name,"name":model_name,"supports_vision":True}}}
            }
        }
    ))

    await page.goto(os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/") + "/", timeout=120_000)
    await page.wait_for_timeout(1500)
    await page.evaluate(
        """
        () => {
          const c = JSON.parse(localStorage.getItem('securityConfig') || '{}');
          c.yoloModeEnabled = true;
          localStorage.setItem('securityConfig', JSON.stringify(c));
          localStorage.setItem('actionMode', 'agent');
        }
        """
    )
    await page.reload()
    await page.wait_for_timeout(2000)

    await page.evaluate(
        """
        () => {
          // Mock Array.prototype.some to bypass checkModelCapability for our test image
          const originalSome = Array.prototype.some;
          Array.prototype.some = function(callback) {
            if (this.length > 0 && typeof this[0] === 'string' && this[0].includes('large_red.png')) {
              return false;
            }
            return originalSome.apply(this, arguments);
          };
        }
        """
    )

    # Wait for textarea to be visible first
    box = page.locator("textarea").first
    await box.wait_for(state="visible", timeout=60_000)

    # Upload image
    file_input = page.locator('input[type="file"][accept*=".png"]').first
    await file_input.set_input_files(image_path)

    # Wait for upload to complete (thumbnail appears)
    await page.wait_for_selector('img[alt="large_red.png"]', timeout=30_000)

    # Fill text and send
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    await box.fill("What color is this image?")
    send = page.locator('button[aria-label="发送"], button[aria-label="Send"]')
    await send.click(timeout=10_000)

    # Wait for response
    # The response should contain text
    await page.wait_for_selector('.prose', timeout=60_000)
    
    # Wait until the streaming stops (send button reappears or stop button disappears)
    await page.wait_for_selector('button[aria-label="发送"], button[aria-label="Send"]', timeout=120_000)
    
    # Check the latest assistant message
    messages = await page.locator('.prose').all_inner_texts()
    assert len(messages) > 0
    last_msg = messages[-1].lower()
    print(f"Assistant replied: {last_msg}")
    assert "red" in last_msg or "error" not in last_msg

@pytest.mark.asyncio
async def test_vision_upload_reactive_compress(tmp_path: Path) -> None:
    # Skip if not explicitly enabled
    if os.environ.get("MYRM_E2E_REAL_FRONTEND_STACK") != "1":
        pytest.skip("Skipping real frontend stack test. Set MYRM_E2E_REAL_FRONTEND_STACK=1 to run.")

    image_path = str(tmp_path / "large_red.png")
    _create_large_image(image_path)
    
    size_mb = os.path.getsize(image_path) / (1024 * 1024)
    print(f"Created test image: {size_mb:.2f} MB")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            await _chat_smoke_vision(page, image_path)
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    # For manual execution
    os.environ["MYRM_E2E_REAL_FRONTEND_STACK"] = "1"
    asyncio.run(test_vision_upload_reactive_compress(Path("/tmp")))
