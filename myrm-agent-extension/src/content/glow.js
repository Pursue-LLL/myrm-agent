/**
 * Content Script — Glow Visual Feedback
 *
 * Shows a subtle glowing border around the viewport when Agent is
 * actively operating on the current page. Injected programmatically
 * by the background service worker (not via manifest content_scripts)
 * to avoid unnecessary overhead on pages that aren't being automated.
 */

(() => {
  const GLOW_ID = "myrm-agent-glow";
  const GLOW_COLOR = "rgba(99, 102, 241, 0.6)";

  let glowEl = null;

  function createGlow() {
    if (glowEl) return;
    glowEl = document.createElement("div");
    glowEl.id = GLOW_ID;
    glowEl.style.cssText = [
      "position: fixed",
      "inset: 0",
      "pointer-events: none",
      "z-index: 2147483646",
      `box-shadow: inset 0 0 30px 4px ${GLOW_COLOR}`,
      "border-radius: 0",
      "opacity: 0",
      "transition: opacity 0.4s ease",
    ].join(";");
    document.documentElement.appendChild(glowEl);
  }

  function showGlow() {
    createGlow();
    requestAnimationFrame(() => {
      if (glowEl) glowEl.style.opacity = "1";
    });
  }

  function hideGlow() {
    if (!glowEl) return;
    glowEl.style.opacity = "0";
    setTimeout(() => {
      if (glowEl && glowEl.parentNode) {
        glowEl.parentNode.removeChild(glowEl);
        glowEl = null;
      }
    }, 500);
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "glow") {
      if (msg.active) {
        showGlow();
      } else {
        hideGlow();
      }
    }
  });
})();
