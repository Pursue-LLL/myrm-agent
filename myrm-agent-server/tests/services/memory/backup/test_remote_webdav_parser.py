"""WebDAV directory listing parser: which entries count as backups and how their names are read.

[INPUT]
app.services.memory.backup.backup_remote::_parse_webdav_multistatus

[OUTPUT]
Which PROPFIND entries become backup files, and that each name comes back as it was uploaded.

[POS]
Pure parser tests on literal XML answers; no network and no strategy.
"""

from __future__ import annotations

from app.services.memory.backup.backup_remote import _parse_webdav_multistatus


class TestWebDAVXMLParser:
    def test_parse_empty_response(self):
        result = _parse_webdav_multistatus("")
        assert result == []

    def test_parse_valid_multistatus(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/myrm-backups/</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>0</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/myrm-backups/myrm.20250101120000.myhost.linux.json.gz</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>4096</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""
        result = _parse_webdav_multistatus(xml)
        assert len(result) == 1
        assert result[0].file_name == "myrm.20250101120000.myhost.linux.json.gz"
        assert result[0].size_bytes == 4096

    def test_parse_filters_non_gz_files(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/backups/readme.txt</d:href>
    <d:propstat><d:prop>
      <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
      <d:getcontentlength>100</d:getcontentlength>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        result = _parse_webdav_multistatus(xml)
        assert len(result) == 0

    def test_parse_returns_names_as_they_were_uploaded(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/myrm-backups/myrm.20260101000000.%E5%B0%8F%E6%98%8E.linux.json.gz</d:href>
    <d:propstat><d:prop><d:getcontentlength>10</d:getcontentlength></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>http://dav.example.com/myrm-backups/myrm.20260101000000.my%20laptop.linux.json.gz</d:href>
    <d:propstat><d:prop><d:getcontentlength>10</d:getcontentlength></d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        names = [f.file_name for f in _parse_webdav_multistatus(xml)]
        assert names == ["myrm.20260101000000.小明.linux.json.gz", "myrm.20260101000000.my laptop.linux.json.gz"]

    def test_parse_skips_names_that_decode_into_a_path(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/myrm-backups/..%2F..%2Fsecret.gz</d:href>
    <d:propstat><d:prop><d:getcontentlength>10</d:getcontentlength></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/myrm-backups/myrm.20260101000000.laptop.linux.json.gz</d:href>
    <d:propstat><d:prop><d:getcontentlength>10</d:getcontentlength></d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        names = [f.file_name for f in _parse_webdav_multistatus(xml)]
        assert names == ["myrm.20260101000000.laptop.linux.json.gz"]

    def test_parse_handles_missing_length(self):
        xml = """<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/backups/test.json.gz</d:href>
    <d:propstat><d:prop>
      <d:getlastmodified>Sat, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
    </d:prop></d:propstat>
  </d:response>
</d:multistatus>"""
        result = _parse_webdav_multistatus(xml)
        assert len(result) == 1
        assert result[0].size_bytes == 0
