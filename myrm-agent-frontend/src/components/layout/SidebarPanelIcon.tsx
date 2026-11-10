/**
 * 侧边栏面板图标
 *
 * [INPUT]
 * - 无
 *
 * [OUTPUT]
 * - SidebarPanelIcon: 收起 / 展开侧边栏按钮共用的面板字形
 *
 * [POS]
 * ContentSidebar 的展开按钮与 ChatSidebarContent 的收起按钮显示同一个字形；装饰性，名称由所在按钮的 aria-label 提供。
 */

export function SidebarPanelIcon() {
  return (
    <svg width="20" height="20" fill="none" viewBox="0 0 20 20" className="text-muted-foreground" aria-hidden="true">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M2.167 6.667A2.833 2.833 0 0 1 5 3.833h2.708v12.334H5a2.833 2.833 0 0 1-2.833-2.834V6.667ZM9.042 17.5H5a4.167 4.167 0 0 1-4.167-4.167V6.667A4.167 4.167 0 0 1 5 2.5h10a4.167 4.167 0 0 1 4.167 4.167v6.666A4.167 4.167 0 0 1 15 17.5H9.042Zm0-13.667H15a2.833 2.833 0 0 1 2.833 2.834v6.666A2.833 2.833 0 0 1 15 16.167H9.042V3.833ZM3.583 6.5c0-.368.336-.667.75-.667H5.75c.414 0 .75.299.75.667 0 .368-.336.667-.75.667H4.333c-.414 0-.75-.299-.75-.667Zm.75 1.833c-.414 0-.75.299-.75.667 0 .368.336.667.75.667H5.75c.414 0 .75-.299.75-.667 0-.368-.336-.667-.75-.667H4.333Z"
        fill="currentColor"
      />
    </svg>
  );
}
