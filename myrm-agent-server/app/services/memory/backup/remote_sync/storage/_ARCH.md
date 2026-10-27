# services/memory/backup/remote_sync/storage/

## 架构概述

用户自有存储（WebDAV / S3 兼容）的适配层：把「上传、下载、列表、删除、连通性」统一成 `RemoteBackupStrategy`，运行器与定时任务只依赖这份契约，不接触 `httpx` / `aioboto3`。

约定（代码为准）：

- **写操作失败返回 `False`，不抛**：上传、下载、删除、连通性检测把失败记日志后如实返回。
- **列表读不到就抛，绝不返回空列表冒充「没有备份」**：存储端拒绝为 `RemoteStorageError`，传输错误原样抛出。只有 WebDAV 文件夹尚不存在（HTTP 404）才是空，因为首次上传会创建它。S3 只读第一页（最多 1000 个对象）。
- **WebDAV 列表只认文件夹的直接子项**：文件名先做百分号解码（与上传时的名字一致），解码后含路径分隔符或不以 `.gz` 结尾的条目直接跳过。
- **按需加载依赖**：`httpx`、`aioboto3` 在首次使用时才导入，未配置远程备份时不加载。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出契约与两种存储的策略和配置，调用方只从这里导入 | ✅ |
| `base.py` | 核心 | 契约：`RemoteBackupStrategy`（upload/download/list_files/delete/check_connection）、`RemoteBackupFile`、`RemoteStorageError` | ✅ |
| `webdav.py` | 核心 | WebDAV（坚果云、Nextcloud、ownCloud 等）：`WebDAVBackupConfig`、`WebDAVBackupStrategy`、PROPFIND 207 响应解析 | ✅ |
| `s3.py` | 核心 | S3 兼容存储（AWS S3、MinIO、阿里云 OSS、Cloudflare R2 等）：`S3BackupConfig`、`S3BackupStrategy` | ✅ |

## 依赖方向

`remote_sync/runner.py`、`remote_sync/job.py`、`app/api/memory/operations/backup_remote.py` → 本目录。本目录只依赖标准库与第三方客户端，不依赖包内其他模块：适配器不知道自己被谁调用。
