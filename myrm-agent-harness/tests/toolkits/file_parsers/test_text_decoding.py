"""Text decoding: UTF-8, Unicode byte-order marks and identifiable legacy encodings decode exactly; whatever cannot be
read as text is refused instead of being turned into garbage that looks like text."""

from __future__ import annotations

import codecs
import io
import zipfile
from pathlib import Path
from random import Random

import pytest

from myrm_agent_harness.toolkits.file_parsers import TextDecodingError, TextParser, decode_text_bytes
from myrm_agent_harness.toolkits.file_parsers.csv_parser import CsvParser
from myrm_agent_harness.toolkits.file_parsers.text_decoding import read_text_file

_REPLACEMENT = "\ufffd"
_UNIDENTIFIED = "could not be identified reliably"

# Plain prose per locale, long enough for the detector to be decisive.
_SIMPLIFIED_CHINESE = (
    "知识库编译流程会先读取原始资料，再由模型提炼要点并写入对应的页面。\n"
    "如果资料的编码无法确认，系统宁可明确拒绝，也不会把乱码写进知识库。\n"
    "每个页面都会记录来源，方便之后回溯和复核。\n"
    "日志文件通常按天滚动，旧的日志会被压缩后归档保存。\n"
    "团队每周同步一次进展，遇到阻塞的事项会在群里及时说明。\n"
)
_TRADITIONAL_CHINESE = (
    "知識庫編譯流程會先讀取原始資料，再由模型提煉重點並寫入對應的頁面。\n"
    "如果資料的編碼無法確認，系統寧可明確拒絕，也不會把亂碼寫進知識庫。\n"
    "每個頁面都會記錄來源，方便之後回溯與複核。\n"
    "日誌檔案通常按天滾動，舊的日誌會被壓縮後歸檔保存。\n"
    "團隊每週同步一次進度，遇到阻塞的事項會在群組裡及時說明。\n"
)
_JAPANESE = (
    "ナレッジベースのコンパイルでは、まず元の資料を読み込み、モデルが要点をまとめて対応するページに書き込みます。\n"
    "資料の文字コードが確認できない場合、システムは文字化けしたまま保存するよりも、はっきりと拒否します。\n"
    "それぞれのページには出典が記録され、あとから確認し直すことができます。\n"
    "ログファイルは通常、日ごとに切り替えられ、古いものは圧縮して保管されます。\n"
    "チームは毎週進捗を共有し、問題があればすぐにチャットで知らせます。\n"
)
_KOREAN = (
    "지식 베이스 컴파일은 먼저 원본 자료를 읽고, 모델이 핵심 내용을 정리해서 해당 페이지에 기록합니다.\n"
    "자료의 인코딩을 확인할 수 없으면 시스템은 깨진 글자를 저장하는 대신 분명하게 거부합니다.\n"
    "모든 페이지에는 출처가 남아 있어서 나중에 다시 확인할 수 있습니다.\n"
    "로그 파일은 보통 하루 단위로 교체되며 오래된 파일은 압축되어 보관됩니다.\n"
    "팀은 매주 진행 상황을 공유하고 문제가 생기면 곧바로 채팅으로 알립니다.\n"
)
_WESTERN = (
    "Über die Straße läuft ein süßer Hund, und Müller möchte außerdem eine größere Tasse wählen.\n"
    "Le café de l’école est fermé à cause de la fête, mais « la boulangerie » reste ouverte.\n"
    "Preis: 25 € – „günstig“ und „zuverlässig“.\n"
)
_MARKDOWN = (
    "# 部署说明\n\n"
    "1. 运行 `make build` 生成产物。\n"
    "2. 把 `dist/` 目录上传到服务器。\n\n"
    "| 环境 | 地址 |\n| --- | --- |\n| 测试 | http://test.example.com |\n| 生产 | https://www.example.com |\n\n"
    "```bash\nexport APP_ENV=production\nsystemctl restart app\n```\n"
    "注意：发布前请先备份数据库，并确认监控告警已经开启。\n"
)
_CSV = (
    "姓名,部门,城市,备注\n"
    "张三,研发部,上海,负责检索服务的维护\n"
    "李四,产品部,北京,负责知识库的需求整理\n"
    "王五,运营部,深圳,负责用户反馈的跟进\n"
)

_LEGACY_TEXTS = [
    pytest.param(_SIMPLIFIED_CHINESE, "gbk", id="gbk"),
    pytest.param(_SIMPLIFIED_CHINESE, "gb18030", id="gb18030"),
    pytest.param(_MARKDOWN, "gbk", id="gbk-markdown-with-code"),
    pytest.param(_CSV, "gbk", id="gbk-csv"),
    pytest.param(_TRADITIONAL_CHINESE, "big5", id="big5"),
    pytest.param(_JAPANESE, "shift_jis", id="shift-jis"),
    pytest.param(_JAPANESE, "euc_jp", id="euc-jp"),
    pytest.param(_KOREAN, "euc_kr", id="euc-kr"),
    pytest.param(_WESTERN, "cp1252", id="windows-1252"),
]


class TestUnicode:
    @pytest.mark.parametrize("text", ["", "plain ascii", _SIMPLIFIED_CHINESE, _JAPANESE, "emoji \U0001f600 and 汉字"])
    def test_utf8_is_decoded_exactly(self, text: str) -> None:
        assert decode_text_bytes(text.encode("utf-8")) == text

    def test_utf8_byte_order_mark_is_dropped(self) -> None:
        assert decode_text_bytes(codecs.BOM_UTF8 + "标题\n".encode()) == "标题\n"

    def test_valid_utf8_never_reaches_the_detector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def refuse(*_: object, **__: object) -> None:
            raise AssertionError("the encoding detector must not run for valid UTF-8")

        monkeypatch.setattr("charset_normalizer.from_bytes", refuse)

        assert decode_text_bytes(_SIMPLIFIED_CHINESE.encode("utf-8")) == _SIMPLIFIED_CHINESE

    @pytest.mark.parametrize(
        ("byte_order_mark", "codec"),
        [
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
            (codecs.BOM_UTF32_LE, "utf-32-le"),
            (codecs.BOM_UTF32_BE, "utf-32-be"),
        ],
    )
    def test_utf16_and_utf32_with_a_byte_order_mark_decode_exactly(self, byte_order_mark: bytes, codec: str) -> None:
        text = "标题 heading\n" + _SIMPLIFIED_CHINESE

        assert decode_text_bytes(byte_order_mark + text.encode(codec)) == text

    def test_utf16_without_a_byte_order_mark_is_binary(self) -> None:
        with pytest.raises(TextDecodingError, match="binary"):
            decode_text_bytes(_SIMPLIFIED_CHINESE.encode("utf-16-le"))


class TestDamagedUtf8:
    def test_a_stray_byte_becomes_one_replacement_character(self) -> None:
        before, after = _SIMPLIFIED_CHINESE[:25], _SIMPLIFIED_CHINESE[25:]

        assert decode_text_bytes(before.encode() + b"\xff" + after.encode()) == before + _REPLACEMENT + after

    def test_a_truncated_last_character_becomes_one_replacement_character(self) -> None:
        text = "每个页面都会记录来源，方便之后回溯和复核。"

        assert decode_text_bytes(text.encode()[:-1]) == text[:-1] + _REPLACEMENT

    def test_a_few_latin1_bytes_in_a_utf8_document_are_replaced(self) -> None:
        data = _SIMPLIFIED_CHINESE.encode() + b"caf\xe9\n" + _SIMPLIFIED_CHINESE.encode()

        text = decode_text_bytes(data)

        assert text == _SIMPLIFIED_CHINESE + "caf" + _REPLACEMENT + "\n" + _SIMPLIFIED_CHINESE

    def test_a_stray_byte_in_ascii_text_is_replaced(self) -> None:
        """No encoding fits a lone undefined byte, and a single one in tens of thousands is no sign of another encoding."""
        prose = "plain ascii text. " * 3000

        assert decode_text_bytes(prose.encode() + b"\x81 end") == prose + _REPLACEMENT + " end"


class TestLegacyEncodings:
    @pytest.mark.parametrize(("text", "encoding"), _LEGACY_TEXTS)
    def test_text_is_decoded_exactly(self, text: str, encoding: str) -> None:
        assert decode_text_bytes(text.encode(encoding)) == text

    @pytest.mark.parametrize(
        ("text", "encoding"),
        [("Café", "cp1252"), ("Façade déjà vu", "cp1252"), ("naïve résumé", "latin-1")],
    )
    def test_a_few_accented_letters_in_a_western_encoding_are_read(self, text: str, encoding: str) -> None:
        assert decode_text_bytes(text.encode(encoding)) == text

    def test_markdown_dense_with_code_symbols_is_read(self) -> None:
        """Code and Markdown syntax hold a larger share of symbols than the detector's default tolerance allows."""
        text = (
            "def run(task: str) -> str:  # 执行任务\n"
            "| `timeout` | 超时时间，单位为秒 |\n"
            "- **重试**：`3` 次；**间隔**：`2s`\n"
        )

        assert decode_text_bytes(text.encode("gbk")) == text

    def test_a_large_document_is_decoded_exactly(self) -> None:
        text = _SIMPLIFIED_CHINESE * 4000

        assert decode_text_bytes(text.encode("gbk")) == text

    @pytest.mark.parametrize("separator", [" ", "\n"], ids=["same-line", "next-line"])
    def test_text_after_a_long_ascii_stretch_is_read_from_where_it_starts(self, separator: str) -> None:
        """The evidence is at the end of the file: judging from its first 64 KiB would decode the rest as garbage."""
        text = ("log entry\n" if separator == "\n" else "x") * 150_000 + separator + _SIMPLIFIED_CHINESE

        assert decode_text_bytes(text.encode("gbk")) == text

    def test_text_after_a_long_stretch_without_ascii_is_read(self) -> None:
        dense = _SIMPLIFIED_CHINESE.replace("，", "").replace("。", "").replace("\n", "") * 400
        text = "x" * 150_000 + " " + dense

        assert decode_text_bytes(text.encode("gb18030")) == text


class TestRefusal:
    def test_a_short_legacy_text_is_refused(self) -> None:
        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes("你好，世界".encode("gbk"))

    @pytest.mark.parametrize(
        ("text", "encoding"),
        [
            pytest.param(_SIMPLIFIED_CHINESE[:14], "gbk", id="gbk"),
            pytest.param(_TRADITIONAL_CHINESE[:14], "big5", id="big5"),
            pytest.param(_JAPANESE[:14], "shift_jis", id="shift-jis"),
        ],
    )
    def test_a_double_byte_text_with_little_evidence_is_refused(self, text: str, encoding: str) -> None:
        """A dozen characters fit several encodings alike: the detector's pick may be right, but it is not trusted."""
        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes(text.encode(encoding))

    @pytest.mark.parametrize("length", [16, 18, 20])
    def test_a_text_that_two_encodings_read_about_equally_well_is_refused(self, length: int) -> None:
        """The detector's pick must beat every other reading by a margin; a close call is refused, not guessed."""
        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes(_JAPANESE[:length].encode("euc_jp"))

    def test_an_unsupported_encoding_is_refused(self) -> None:
        cyrillic = "Это длинный русский текст в кодировке Windows-1251, которую система не поддерживает. " * 6

        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes(cyrillic.encode("cp1251"))

    def test_text_in_two_encodings_is_refused(self) -> None:
        data = _SIMPLIFIED_CHINESE.encode("utf-8") + _SIMPLIFIED_CHINESE.encode("gbk")

        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes(data)

    def test_a_stray_byte_in_a_legacy_text_is_refused(self) -> None:
        before, after = _SIMPLIFIED_CHINESE[:20], _SIMPLIFIED_CHINESE[20:]

        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes(before.encode("gbk") + b"\xff" + after.encode("gbk"))

    def test_a_stray_byte_beyond_the_sampled_window_is_refused_just_the_same(self) -> None:
        """The verdict must not depend on whether the damage happens to fall inside the window the encoding is judged from."""
        data = (_SIMPLIFIED_CHINESE * 4000).encode("gbk")

        with pytest.raises(TextDecodingError, match=_UNIDENTIFIED):
            decode_text_bytes(data[:-1] + b"\xff" + data[-1:])

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(Random(0).randbytes(4096), id="random-bytes"),
            pytest.param(b"MZ\x90\x00" + bytes(range(256)) * 4, id="executable"),
            pytest.param(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n", id="pdf"),
            pytest.param(b"\x00\x01\x02\x03\xfe\xff" * 100, id="control-bytes"),
        ],
    )
    def test_binary_data_is_refused(self, data: bytes) -> None:
        with pytest.raises(TextDecodingError, match="binary"):
            decode_text_bytes(data)

    def test_an_archive_is_refused(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", _SIMPLIFIED_CHINESE)

        with pytest.raises(TextDecodingError, match="binary"):
            decode_text_bytes(buffer.getvalue())


class TestFiles:
    def test_a_file_is_read_with_unix_line_endings(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.txt"
        path.write_bytes(_SIMPLIFIED_CHINESE.replace("\n", "\r\n").encode("gbk") + b"tail\rend\n")

        assert read_text_file(path) == _SIMPLIFIED_CHINESE + "tail\nend\n"

    async def test_text_parser_reads_a_legacy_file(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.md"
        path.write_bytes(_MARKDOWN.encode("gbk"))

        assert await TextParser().parse(str(path)) == _MARKDOWN

    async def test_text_parser_drops_the_utf8_byte_order_mark(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.md"
        path.write_bytes(codecs.BOM_UTF8 + "# 标题\n".encode())

        assert await TextParser().parse(str(path)) == "# 标题\n"

    async def test_text_parser_refuses_a_binary_file(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.txt"
        path.write_bytes(Random(1).randbytes(2048))

        with pytest.raises(TextDecodingError, match="binary"):
            await TextParser().parse(str(path))

    async def test_csv_parser_reads_a_legacy_file(self, tmp_path: Path) -> None:
        path = tmp_path / "staff.csv"
        path.write_bytes(_CSV.encode("gbk"))

        table = await CsvParser().parse(str(path))

        assert table.splitlines()[0] == "| 姓名 | 部门 | 城市 | 备注 |"
        assert "| 李四 | 产品部 | 北京 | 负责知识库的需求整理 |" in table
