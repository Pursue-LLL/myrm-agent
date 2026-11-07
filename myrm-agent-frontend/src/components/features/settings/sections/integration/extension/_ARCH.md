# integration/extension/

Extension Bridge UI subcomponents.

| File                            | Role                                                                                                                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ExtensionClipAgentField.tsx`   | Wiki clip target agent Select (SSOT `/extension/clip-agent`)                                                                                            |
| `useExtensionBridge.ts`         | State and actions for the bridge: 5 s status polling, pairing, access-policy edits (domains, allow-all, tab pause) through one shared write, disconnect |
| `ExtensionConnectionPanels.tsx` | Connection info card with the relay capability matrix, connection status bar, setup guide                                                               |
| `ExtensionAccessPanels.tsx`     | Authorized domains panel (allow-all switch, domain chips) and the open tabs panel (pause / resume)                                                      |

`ExtensionBridgeSection.tsx`（父目录）只持有 `useExtensionBridge` 并组装上述区块；配对、域名、allow-all、**可用标签页暂停/恢复**（`paused_tab_ids`）的写入都在 hook 内。
