"""Memory backup subpackage — one portable snapshot, stored on the volume or on WebDAV/S3.

[POS]
记忆备份域。snapshot 为本地与远程共用的快照契约；volume_store + service 为沙箱持久卷上的本地备份；
remote_sync/ 为远程备份：存储适配（WebDAV/S3）、运行器与云端定时备份。
"""
