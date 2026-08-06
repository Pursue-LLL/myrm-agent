/**
 * Content script — capture page/selection HTML and remote images (credentialed fetch) for wiki clip.
 */

(() => {
  const MAX_ASSETS = 20;
  const MAX_ASSET_BYTES = 5 * 1024 * 1024;
  const collectImageUrls =
    globalThis.MyrmClipImageUrls?.collectImageUrls ||
    ((_html, _base, _max) => {
      throw new Error("MyrmClipImageUrls not loaded");
    });

  function selectionHtml() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return "";
    const range = sel.getRangeAt(0);
    const div = document.createElement("div");
    div.appendChild(range.cloneContents());
    return div.innerHTML;
  }

  function pageHtml() {
    const article = document.querySelector("article");
    const main = document.querySelector("main");
    const node = article || main || document.body;
    return node ? node.innerHTML : document.documentElement.outerHTML;
  }

  async function fetchAsset(url) {
    const resp = await fetch(url, { credentials: "include", redirect: "follow" });
    if (!resp.ok) return null;
    const blob = await resp.blob();
    if (blob.size > MAX_ASSET_BYTES) return null;
    const buffer = await blob.arrayBuffer();
    return {
      source_url: url,
      content_type: blob.type || "application/octet-stream",
      data: new Uint8Array(buffer),
    };
  }

  async function buildClipPayload(mode) {
    const html = mode === "selection" ? selectionHtml() : pageHtml();
    if (mode === "selection" && !html.trim()) {
      throw new Error("Empty selection");
    }
    const imageUrls = collectImageUrls(html, location.href, MAX_ASSETS);
    const assets = [];
    for (const url of imageUrls) {
      try {
        const item = await fetchAsset(url);
        if (item) assets.push(item);
      } catch {
        /* skip failed asset */
      }
    }
    return {
      source_url: location.href,
      title: document.title || location.href,
      clip_mode: mode === "selection" ? "selection" : "full_page",
      html,
      markdown: "",
      folder_path: "",
      queue_compile: false,
      assets,
    };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type !== "clip_to_wiki") return false;
    const mode = msg.mode === "selection" ? "selection" : "full_page";
    buildClipPayload(mode)
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
    return true;
  });
})();
