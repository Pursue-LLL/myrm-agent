# services/memory/backup/remote_sync/storage/

## 架构概述

用户自有存储（WebDAV / S3 兼容）的适配层：把「上传、下载、列表、删除、连通性」统一成 `RemoteBackupStrategy`，运行器与定时任务只依赖这份契约，不接触 `httpx` / `aioboto3`。

约定（代码为准）：

- **写操作失败返回 `False`，不抛**：上传、下载、删除、连通性检测把失败记日志后如实返回。
- **列表读不到就抛，绝不返回空列表冒充「没有备份」**：存储端拒绝为 `RemoteStorageError`，传输错误原样抛出。只有 WebDAV 文件夹尚不存在（HTTP 404）才是空，因为首次上传会创建它。
- **S3 列表读完每一页**：`list_objects_v2` 每次最多返回 1000 个键且按键序排列，同一前缀下排在 `myrm.` 之前的其它文件会把备份挤出第一页，所以沿 continuation token 一直读到不再截断。超过 `_LIST_PAGE_LIMIT`（100 页）或页被截断却没有 token 时抛 `RemoteStorageError`，不返回读了一半的列表；用户需要换一个更具体的前缀。
- **WebDAV 列表只认文件夹的直接子项**：文件名先做百分号解码（与上传时的名字一致），解码后含路径分隔符或不以 `.gz` 结尾的条目直接跳过。
- **按需加载依赖**：`httpx`、`aioboto3` 在首次使用时才导入，未配置远程备份时不加载。
- **S3 的 TLS 上下文跟随企业网络兼容设置**：aiobotocore 用自带的构建器与固定的 CA 包建上下文，不经过 `ssl.create_default_context`，全局策略碰不到它。`s3.py` 的会话子类在设置打开时改用 `ssl.create_default_context()`（系统证书库加环境变量指向的 CA 包，只去掉严格标志，证书链、主机名、有效期仍校验），关闭时保持 aiobotocore 原样。WebDAV 经 `httpx` 取上下文，本来就在全局策略内。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出契约与两种存储的策略和配置，调用方只从这里导入 | ✅ |
| `base.py` | 核心 | 契约：`RemoteBackupStrategy`（upload/download/list_files/delete/check_connection）、`RemoteBackupFile`、`RemoteStorageError` | ✅ |
| `webdav.py` | 核心 | WebDAV（坚果云、Nextcloud、ownCloud 等）：`WebDAVBackupConfig`、`WebDAVBackupStrategy`、PROPFIND 207 响应解析 | ✅ |
| `s3.py` | 核心 | S3 兼容存储（AWS S3、MinIO、阿里云 OSS、Cloudflare R2 等）：`S3BackupConfig`、`S3BackupStrategy`，以及按企业网络兼容设置取 TLS 上下文的 aiobotocore 会话类 | ✅ |

## 依赖方向

`remote_sync/runner.py`、`remote_sync/job.py`、`app/api/memory/operations/backup_remote.py` → 本目录。本目录只依赖标准库、第三方客户端与 harness 的 `infra.tls_compat`（只读企业网络兼容设置），不依赖本目录以外的 `app` 模块：适配器不知道自己被谁调用。
