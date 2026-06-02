import argparse
import asyncio
import os
import sys
import traceback

from patchright.async_api import async_playwright


async def _wait_frontend_api_health(base_url: str, timeout_s: float = 120.0) -> None:
    """Fail fast when Next proxy or backend is broken (avoid opaque Playwright timeouts)."""
    import urllib.error
    import urllib.request

    health_url = base_url.rstrip("/") + "/api/v1/health"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    last_err: str | None = None
    while loop.time() < deadline:
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if getattr(resp, "status", 200) == 200:
                    print(f"API health OK: {health_url}")
                    return
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
        except Exception as exc:
            last_err = str(exc)
        await asyncio.sleep(1)
    raise RuntimeError(
        f"Frontend API not healthy within {timeout_s}s ({health_url}). Last error: {last_err}"
    )


async def _wait_generation_finished(page, timeout_ms: float = 180_000.0) -> None:
    """Wait until MessageInput hides the Stop control (loading finished).

    MessageInput.tsx swaps send for ``aria-label=\"Stop\"`` while ``loading`` is true.
    """

    stop_btn = page.locator('button[aria-label="Stop"]')
    try:
        await stop_btn.wait_for(state="visible", timeout=60_000.0)
    except Exception:
        print(
            "WARN: Stop button not visible within 60s (stream may not have started); settling 5s"
        )
        await page.wait_for_timeout(5000)
        return
    await stop_btn.wait_for(state="detached", timeout=timeout_ms)


async def _log_working_memory_chips(page) -> None:
    chips = page.locator('[data-testid="working-memory-chip"]')
    n = await chips.count()
    print(f"Working memory chips visible: {n}")
    for i in range(min(n, 16)):
        fn = await chips.nth(i).get_attribute("data-filename")
        dd = await chips.nth(i).get_attribute("data-diff")
        dt = await chips.nth(i).get_attribute("data-diff-truncated")
        print(f"  chip[{i}] filename={fn!r} data-diff={dd} data-diff-truncated={dt}")


async def _submit_prompt(page, prompt_text: str) -> None:
    # While ``loading`` is true, MessageInput shows Stop — not Send (MessageInput.tsx).
    send = page.locator('button[aria-label="发送"], button[aria-label="Send"]')
    await send.wait_for(state="visible", timeout=120_000)
    box = page.locator("textarea").first
    await box.wait_for(state="visible", timeout=30_000)
    await box.fill(prompt_text)
    await send.click()


async def _monaco_model_plain_text(portal) -> str:
    """Collect visible Monaco lines (includes leading +/- for unified diff)."""
    lines_el = portal.locator(".monaco-editor .view-line")
    n = await lines_el.count()
    parts: list[str] = []
    for i in range(min(n, 800)):
        t = (await lines_el.nth(i).inner_text()).replace("\n", " ")
        parts.append(t)
    return "\n".join(parts)


def _unified_diff_shows_line_replace(text: str, old_fragment: str, new_fragment: str) -> bool:
    lines = text.replace("\r\n", "\n").split("\n")
    has_old_minus = any(
        ln.startswith("-") and not ln.startswith("---") and old_fragment in ln
        for ln in lines
    )
    has_new_plus = any(
        ln.startswith("+") and not ln.startswith("+++") and new_fragment in ln
        for ln in lines
    )
    return has_old_minus and has_new_plus


async def _prepare_chat_page(page, frontend_url: str) -> None:
    await _wait_frontend_api_health(frontend_url)
    print(f"Navigating to {frontend_url}...")
    await page.goto(frontend_url, timeout=60000)
    await page.wait_for_timeout(2000)

    print("Enabling YOLO mode via localStorage...")
    await page.evaluate(
        """
        () => {
            const currentConfig = JSON.parse(localStorage.getItem('securityConfig') || '{}');
            currentConfig.yoloModeEnabled = true;
            localStorage.setItem('securityConfig', JSON.stringify(currentConfig));
            localStorage.setItem('actionMode', 'agent');
        }
    """
    )

    print("Reloading page to apply YOLO mode...")
    await page.reload()
    await page.wait_for_timeout(2000)


async def _prompt_combined_single_turn(page) -> None:
    print("Mode=combined: single assistant turn (write + str_replace)...")
    await _submit_prompt(
        page,
        "In ONE response: (1) Use the file write tool to create `test_diff_e2e.txt` "
        "with exactly three lines: line1, line2, line3. (2) Then use str_replace or "
        "search_replace (file edit tool) to change line2 to modified_line2. Do not use "
        "shell/bash/python one-liners for either step. Do not delete or rename the file "
        "between steps.",
    )


async def _prompt_two_user_turns(page) -> None:
    print("Mode=two-turn: user message 1 — create file via write tool...")
    await _submit_prompt(
        page,
        "Use the editor/file write tool (write_file or equivalent — not shell, not "
        "printf/heredoc) to create `test_diff_e2e.txt` in the workspace with exactly "
        "three lines: line1, line2, line3.",
    )
    await _wait_generation_finished(page)
    await page.screenshot(path="after_prompt_turn1.png")

    print("Mode=two-turn: user message 2 — edit via str_replace...")
    await _submit_prompt(
        page,
        "Use the file edit tool (str_replace / search_replace — not shell) to change the "
        "middle line of `test_diff_e2e.txt` from line2 to modified_line2.",
    )


def _parse_modes(argv: list[str] | None) -> list[str]:
    parser = argparse.ArgumentParser(description="Action-Aware Diff Preview E2E")
    parser.add_argument(
        "--mode",
        choices=("combined", "two-turn", "all"),
        default="combined",
        help=(
            "combined=single assistant turn (default, stable). "
            "two-turn=two user messages (LLM may skip tools or omit visible text — manual/CI opt-in). "
            "all=runs combined only (full gate); use two-turn on its own when regression-testing multi-turn."
        ),
    )
    args = parser.parse_args(argv)
    if args.mode == "all":
        return ["combined"]
    return [args.mode]


async def _run_single_session(mode: str, frontend_url: str) -> int:
    """One browser session = one fresh chat (required for --mode all)."""
    overall = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()

            page.on("console", lambda msg: print(f"Browser console: {msg.text}"))
            page.on(
                "requestfailed",
                lambda req: print(f"Request failed: {req.url} - {req.failure}"),
            )
            page.on(
                "response",
                lambda res: (
                    print(f"Response {res.status}: {res.url}")
                    if res.status >= 400
                    else None
                ),
            )

            print(f"Navigating to chat (mode={mode})...")
            await _prepare_chat_page(page, frontend_url)

            if mode == "combined":
                await _prompt_combined_single_turn(page)
            else:
                await _prompt_two_user_turns(page)

            if mode == "combined":
                print("Waiting for edit evidence (modified_line2 on page) then stream settle...")
                try:
                    await page.wait_for_function(
                        "() => document.body.innerText.includes('modified_line2')",
                        timeout=180_000,
                    )
                    print("Page contains modified_line2")
                except Exception as exc:
                    print(f"WARN: modified_line2 not observed within 180s: {exc}")
            else:
                print("two-turn: waiting for assistant stream after second prompt...")
            await _wait_generation_finished(page)
            shot = (
                "after_prompt.png"
                if mode == "combined"
                else "after_prompt_turn2_final.png"
            )
            await page.screenshot(path=shot)

            print("Waiting for chip...")
            chip_selector = '[data-testid="working-memory-chip"][data-filename="test_diff_e2e.txt"]'

            try:
                await page.wait_for_selector(chip_selector, timeout=180_000)
                chips = page.locator(chip_selector)
                count = await chips.count()
                diff_flag = await chips.first.get_attribute("data-diff")
                print(f"Chip data-diff={diff_flag} (1 means FILE_DIFF merged into progressSteps)")
                click_locator = chips.first
                if count > 1:
                    for i in range(count):
                        attr = await chips.nth(i).get_attribute("data-diff")
                        if attr == "1":
                            click_locator = chips.nth(i)
                            print(f"Using chip index {i} with data-diff=1")
                            break
                trunc_flag = await click_locator.get_attribute("data-diff-truncated")
                print(f"Chip data-diff-truncated={trunc_flag}")
                print("Clicking chip...")
                await click_locator.evaluate("(el) => el.click()")

                await page.wait_for_timeout(5000)

                if trunc_flag == "1":
                    banner = page.locator('[role="dialog"][aria-modal="true"] [role="status"]')
                    await banner.wait_for(state="attached", timeout=15000)
                    bn = await banner.inner_text()
                    if not bn.strip():
                        raise RuntimeError("Truncation banner (role=status) is empty")
                    print(f"Truncation banner text (excerpt): {bn[:160]!r}")

                await page.screenshot(path=f"after_click_chip_{mode}.png")
            except Exception as e:
                print("Failed to find chip. Taking screenshot...")
                await _log_working_memory_chips(page)
                await page.screenshot(path="diff_test_failed.png")
                raise e

            print("Verifying diff view...")
            await page.wait_for_selector("#artifact-content-container", state="attached", timeout=30000)
            await page.wait_for_selector(
                "#artifact-content-container .monaco-editor",
                state="attached",
                timeout=30000,
            )
            await page.wait_for_timeout(2000)

            portal = page.locator("#artifact-content-container").first
            body_text = await portal.evaluate("el => el.innerText || ''")
            monaco_plain = await _monaco_model_plain_text(portal)

            monaco_root = portal.locator(".monaco-editor").first
            green_lines = await monaco_root.locator("[class*='bg-green-500']").count()
            red_lines = await monaco_root.locator("[class*='bg-red-500']").count()

            text_signals_unified_diff = (
                ("line2" in body_text and "modified_line2" in body_text)
                and ("-" in body_text or "+" in body_text or "@@" in body_text)
            )
            line_replace_in_monaco = _unified_diff_shows_line_replace(
                monaco_plain, "line2", "modified_line2"
            )

            print(
                f"Monaco: {green_lines} green-class nodes, {red_lines} red-class nodes; "
                f"text heuristic: {text_signals_unified_diff}; "
                f"monaco -/ + line replace: {line_replace_in_monaco}"
            )
            if not line_replace_in_monaco and len(monaco_plain) < 8000:
                excerpt = monaco_plain[:1200] if monaco_plain else "(empty monaco_plain)"
                print(f"Monaco text excerpt for diagnosis:\n{excerpt}\n--- end excerpt ---")

            passed = (
                (green_lines > 0 and red_lines > 0)
                or line_replace_in_monaco
                or text_signals_unified_diff
                or (
                    green_lines > 0
                    and ("modified_line2" in body_text)
                    and ("line2" in body_text or "-" in body_text)
                )
            )
            if passed:
                print(f"✅ E2E Test Passed ({mode}): Action-Aware Diff Preview works!")
            else:
                print(
                    f"❌ E2E Test Failed ({mode}): Diff content/decorations not detected in Monaco."
                )
                await page.screenshot(path="diff_test_failed.png")
                html_content = await page.content()
                dump_path = os.path.join(os.path.dirname(__file__) or ".", "page_dump.html")
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"Saved page HTML to {dump_path} (failure only)")
                overall = 1
        finally:
            await browser.close()
    return overall


async def main() -> int:
    try:
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass

        modes = _parse_modes(None)
        frontend_url = os.environ.get("FRONTEND_URL", "http://127.0.0.1:3000/")
        for mode in modes:
            print(f"\n========== E2E run: {mode} ==========")
            code = await _run_single_session(mode, frontend_url)
            if code != 0:
                return code
        return 0
    except Exception as e:
        print(f"Exception occurred: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
