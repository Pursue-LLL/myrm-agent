/**
 * Side Panel page context: the active tab and the selected text a message is asked about.
 *
 * [INPUT]
 * - The context bar and selection quote elements; `chrome.tabs` for the active tab
 *
 * [OUTPUT]
 * - createPageContext: `start()` follows the active tab, `setSelection` / `clearSelection` hold the quoted text,
 *   `queryPrefix()` renders both as the lines that precede the user's text in the query
 *
 * [POS] Owns the tab/selection state and its two bars; sidepanel.js only asks for the prefix when it sends a message.
 */

const MAX_TITLE_CHARS = 50;
const MAX_SELECTION_CHARS = 2000;

/**
 * @param {{
 *   bar: HTMLElement,
 *   value: HTMLElement,
 *   dismiss: HTMLElement,
 *   selectionBox: HTMLElement,
 *   selectionText: HTMLElement,
 * }} elements
 */
export function createPageContext({ bar, value, dismiss, selectionBox, selectionText }) {
  let activeTab = null;
  let selected = null;
  let dismissed = false;

  /** @param {chrome.tabs.Tab | undefined} tab */
  function followTab(tab) {
    if (!tab?.url || tab.url.startsWith("chrome://")) return false;
    activeTab = { id: tab.id, title: tab.title || "", url: tab.url };
    return true;
  }

  function showTab() {
    if (dismissed || !activeTab) return;
    const title = activeTab.title || new URL(activeTab.url).hostname;
    value.textContent = title.length > MAX_TITLE_CHARS ? `${title.slice(0, MAX_TITLE_CHARS - 3)}…` : title;
    bar.classList.add("visible");
  }

  return {
    start() {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (followTab(tabs[0])) showTab();
      });
      chrome.tabs.onActivated.addListener((info) => {
        chrome.tabs.get(info.tabId, (tab) => {
          if (!followTab(tab)) return;
          dismissed = false;
          showTab();
        });
      });
      dismiss.addEventListener("click", () => {
        dismissed = true;
        bar.classList.remove("visible");
      });
    },

    /** @param {string | undefined} text */
    setSelection(text) {
      if (!text || !text.trim()) return;
      selected = text.trim().slice(0, MAX_SELECTION_CHARS);
      selectionText.textContent = selected;
      selectionBox.classList.add("visible");
    },

    clearSelection() {
      selected = null;
      selectionBox.classList.remove("visible");
    },

    /** @returns {string} */
    queryPrefix() {
      let prefix = "";
      if (!dismissed && activeTab) prefix = `[Current page: ${activeTab.title} — ${activeTab.url}]\n\n`;
      if (selected) prefix += `[Selected text: "${selected}"]\n\n`;
      return prefix;
    },
  };
}
