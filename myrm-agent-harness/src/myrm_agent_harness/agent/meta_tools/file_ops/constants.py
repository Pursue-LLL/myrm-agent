"""Text Editor 常量定义

包含文件大小限制、格式化常量和三个文件工具共用的参数说明。

[INPUT]
- (none)

[OUTPUT]
- MAX_FILE_READ_SIZE_BYTES, MAX_RANGED_READ_SIZE_BYTES, MAX_FILE_WRITE_SIZE_BYTES, LINE_NUMBER_WIDTH, SEPARATOR_WIDTH, REASON_FIELD_DESCRIPTION

[POS]
文件操作工具的常量层：读写大小上限、行号与分隔符的显示宽度，以及 file_read/file_write/file_edit 共用的 `reason` 参数说明。
"""

# 文件大小限制
MAX_FILE_READ_SIZE_BYTES = 10 * 1024 * 1024  # 最大读取文件大小 10MB
MAX_RANGED_READ_SIZE_BYTES = 100 * 1024 * 1024  # 带行号范围的读取上限 100MB（范围读取是读大文件的唯一出路）
MAX_FILE_WRITE_SIZE_BYTES = 5 * 1024 * 1024  # 最大写入文件大小 5MB（工件限制）

# 格式化常量
LINE_NUMBER_WIDTH = 6  # 行号显示宽度
SEPARATOR_WIDTH = 60  # 分隔符宽度

# 三个文件工具共用的 `reason` 参数说明（模型可见）。该字段会随步骤事件展示在前端步骤详情中，并非只写日志，
# 所以说明必须让模型写给用户看。
REASON_FIELD_DESCRIPTION = "Short note on why, shown to the user in the step details."
