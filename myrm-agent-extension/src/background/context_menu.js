/**
 * Context menu entries and the keyboard shortcut that open the side panel or clip a page.
 *
 * [INPUT]
 * - clip.js::submitClipToWiki (POS: the clip entries)
 * - i18n.js::msg (POS: menu titles)
 *
 * [OUTPUT]
 * - setupContextMenu: (re)create the menu entries
 *
 * [POS] User-initiated entry points other than the popup. Importing it arms the click and shortcut listeners.
 */

import { msg } from "../i18n.js";
import { submitClipToWiki } from "./clip.js";

export function setupContextMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "ask-myrm-agent", title: msg("ctxAskMyrmAgent"), contexts: ["selection"] });
    chrome.contextMenus.create({ id: "ask-myrm-agent-page", title: msg("ctxAskMyrmAgentPage"), contexts: ["page"] });
    chrome.contextMenus.create({ id: "clip-wiki-selection", title: msg("ctxClipWikiSelection"), contexts: ["selection"] });
    chrome.contextMenus.create({ id: "clip-wiki-page", title: msg("ctxClipWikiPage"), contexts: ["page"] });
  });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab?.id) return;
  if (info.menuItemId === "clip-wiki-selection") {
    submitClipToWiki(tab, "selection");
    return;
  }
  if (info.menuItemId === "clip-wiki-page") {
    submitClipToWiki(tab, "full_page");
    return;
  }
  if (info.menuItemId === "ask-myrm-agent" && info.selectionText) {
    chrome.sidePanel.open({ tabId: tab.id }).then(() => {
      setTimeout(() => {
        chrome.runtime.sendMessage({
          type: "context_menu_query", text: info.selectionText,
          prompt: "", url: tab.url, title: tab.title,
        }).catch(() => {});
      }, 300);
    }).catch(() => {});
  }
  if (info.menuItemId === "ask-myrm-agent-page") {
    chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "toggle-sidepanel") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) chrome.sidePanel.open({ tabId: tabs[0].id }).catch(() => {});
    });
  }
});
