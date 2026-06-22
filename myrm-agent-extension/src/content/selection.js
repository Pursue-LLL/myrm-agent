/**
 * Content Script — Selection Capture
 *
 * Monitors text selection on webpages and forwards it to the Side Panel
 * via the background service worker. Lightweight: only fires on mouseup
 * when a non-trivial selection exists.
 */

(() => {
  const MIN_SELECTION_LENGTH = 3;
  const MAX_SELECTION_LENGTH = 2000;
  let lastSent = "";

  document.addEventListener("mouseup", () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;

    const text = sel.toString().trim();
    if (text.length < MIN_SELECTION_LENGTH || text === lastSent) return;

    lastSent = text;
    const truncated = text.length > MAX_SELECTION_LENGTH
      ? text.slice(0, MAX_SELECTION_LENGTH)
      : text;

    chrome.runtime.sendMessage({
      type: "selected_text",
      text: truncated,
      url: location.href,
      title: document.title,
    }).catch(() => {
      // Extension context invalidated or side panel not open — ignore
    });
  });

  // Clear tracked selection when user clicks without selecting
  document.addEventListener("mousedown", () => {
    lastSent = "";
  });
})();
