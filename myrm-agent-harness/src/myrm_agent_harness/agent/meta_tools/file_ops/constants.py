"""Text Editor 常量定义

包含文件大小限制、格式化常量、路径解析模式和三个文件工具共用的参数说明。

[INPUT]
- (none)

[OUTPUT]
- MAX_FILE_READ_SIZE_BYTES, MAX_RANGED_READ_SIZE_BYTES, MAX_FILE_WRITE_SIZE_BYTES 及其 MB 形式, LINE_NUMBER_WIDTH, SEPARATOR_WIDTH, PATH_RANGE_PATTERN, REASON_FIELD_DESCRIPTION

[POS]
文件操作工具的常量层：读写大小上限、行号与分隔符的显示宽度，解析 `file.py:1-50` 行号范围路径的正则，以及 file_read/file_write/file_edit 共用的 `reason` 参数说明。
"""

import re

# 文件大小限制
MAX_FILE_READ_SIZE_BYTES = 10 * 1024 * 1024  # 最大读取文件大小 10MB
MAX_RANGED_READ_SIZE_BYTES = 100 * 1024 * 1024  # 带行号范围的读取上限 100MB（范围读取是读大文件的唯一出路）
MAX_FILE_WRITE_SIZE_BYTES = 5 * 1024 * 1024  # 最大写入文件大小 5MB（工件限制）
MAX_FILE_READ_SIZE_MB = MAX_FILE_READ_SIZE_BYTES / (1024 * 1024)
MAX_FILE_WRITE_SIZE_MB = MAX_FILE_WRITE_SIZE_BYTES / (1024 * 1024)
MAX_FILE_SIZE_MB = MAX_FILE_READ_SIZE_MB  # 用于错误消息显示

# 格式化常量
LINE_NUMBER_WIDTH = 6  # 行号显示宽度
SEPARATOR_WIDTH = 60  # 分隔符宽度

# 路径行号范围解析正则：file.py:1-50 或 file.py:100-
PATH_RANGE_PATTERN = re.compile(r"^(.+):(\d+)-(\d*)$")

# 三个文件工具共用的 `reason` 参数说明（模型可见）。该字段会随步骤事件展示在前端步骤详情中，并非只写日志，
# 所以说明必须让模型写给用户看。
REASON_FIELD_DESCRIPTION = "Short note on why, shown to the user in the step details."
