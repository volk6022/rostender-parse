"""Тесты для src/parser/html_protocol.py — чистые функции, dataclass-ы и async функции."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.parser.html_protocol import (
    ProtocolFile,
    ProtocolParseResult,
    _extract_tenders_data,
    _find_protocol_files,
    _guess_extension,
    _parse_downloaded_file,
    _prioritize_protocols,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_page_html(tender_id: str, tender_data: dict) -> str:
    """Создаёт минимальный HTML с var tendersData = {...};"""
    blob = json.dumps({tender_id: tender_data})
    return f"<html><script>var tendersData = {blob};</script></html>"


def _make_protocol_file(
    file_id: int = 1,
    tender_id: str = "T-100",
    title: str = "Протокол рассмотрения",
    link: str = "/dl/1",
    extension: str | None = "docx",
    size: int = 1024,
    is_protocol: bool = True,
) -> ProtocolFile:
    return ProtocolFile(
        file_id=file_id,
        tender_id=tender_id,
        title=title,
        link=link,
        extension=extension,
        size=size,
        is_protocol=is_protocol,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ProtocolFile / ProtocolParseResult dataclasses
# ═══════════════════════════════════════════════════════════════════════════════


class TestProtocolFile:
    def test_fields(self):
        pf = _make_protocol_file()
        assert pf.file_id == 1
        assert pf.tender_id == "T-100"
        assert pf.title == "Протокол рассмотрения"
        assert pf.link == "/dl/1"
        assert pf.extension == "docx"
        assert pf.size == 1024
        assert pf.is_protocol is True

    def test_none_extension(self):
        pf = _make_protocol_file(extension=None)
        assert pf.extension is None


class TestProtocolParseResult:
    def test_success_result(self):
        r = ProtocolParseResult(
            tender_id="T-1",
            participants_count=3,
            parse_source="html",
            parse_status="success",
            doc_path="/some/path",
            notes="method=direct_count",
        )
        assert r.participants_count == 3
        assert r.parse_status == "success"

    def test_failed_result(self):
        r = ProtocolParseResult(
            tender_id="T-1",
            participants_count=None,
            parse_source=None,
            parse_status="no_protocol",
            doc_path=None,
            notes=None,
        )
        assert r.participants_count is None
        assert r.parse_status == "no_protocol"


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_tenders_data
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractTendersData:
    def test_extracts_by_string_key(self):
        data = {"files_by_date": {"2024-01-01": []}}
        html = _make_page_html("12345", data)
        result = _extract_tenders_data(html, "12345")
        assert result is not None
        assert "files_by_date" in result

    def test_extracts_by_int_key(self):
        """tender_id в JSON как число, ищем строкой."""
        inner = {"files_by_date": {}}
        blob = json.dumps({12345: inner})
        html = f"<script>var tendersData = {blob};</script>"
        result = _extract_tenders_data(html, "12345")
        assert result is not None

    def test_single_key_fallback(self):
        """Если один ключ и не совпадает — всё равно берём его."""
        inner = {"files_by_date": {"d": []}}
        blob = json.dumps({"OTHER_KEY": inner})
        html = f"<script>var tendersData = {blob};</script>"
        result = _extract_tenders_data(html, "12345")
        assert result is not None
        assert result == inner

    def test_multiple_keys_no_match_returns_none(self):
        blob = json.dumps({"A": {}, "B": {}})
        html = f"<script>var tendersData = {blob};</script>"
        result = _extract_tenders_data(html, "12345")
        assert result is None

    def test_no_tenders_data_returns_none(self):
        html = "<html><body>Hello</body></html>"
        result = _extract_tenders_data(html, "12345")
        assert result is None

    def test_invalid_json_returns_none(self):
        html = "<script>var tendersData = {broken json};</script>"
        result = _extract_tenders_data(html, "12345")
        assert result is None

    def test_multiline_script(self):
        inner = {"files_by_date": {}}
        blob = json.dumps({"T1": inner}, indent=2)
        html = f"<script>\nvar tendersData = {blob};\n</script>"
        result = _extract_tenders_data(html, "T1")
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# _guess_extension
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuessExtension:
    def test_ext_field(self):
        assert _guess_extension({"ext": "PDF"}) == "pdf"

    def test_fsid_with_dot(self):
        assert _guess_extension({"fsid": "file.DOCX"}) == "docx"

    def test_no_ext_no_fsid(self):
        assert _guess_extension({}) is None

    def test_fsid_no_dot(self):
        assert _guess_extension({"fsid": "abc123"}) is None

    def test_ext_takes_priority_over_fsid(self):
        assert _guess_extension({"ext": "html", "fsid": "file.pdf"}) == "html"


# ═══════════════════════════════════════════════════════════════════════════════
# _find_protocol_files
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindProtocolFiles:
    def test_finds_by_is_protocol_flag(self):
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T1",
                        "title": "Документ",
                        "link": "/a",
                        "size": 100,
                        "is_protocol": True,
                    },
                ]
            }
        }
        result = _find_protocol_files(tender_data)
        assert len(result) == 1
        assert result[0].is_protocol is True

    def test_finds_by_title_keyword(self):
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T1",
                        "title": "Протокол заседания",
                        "link": "/a",
                        "size": 100,
                    },
                ]
            }
        }
        result = _find_protocol_files(tender_data)
        assert len(result) == 1

    def test_flag_takes_priority_over_title(self):
        """Если есть is_protocol=True, файлы по заголовку НЕ включаются."""
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T1",
                        "title": "flagged",
                        "link": "/a",
                        "size": 100,
                        "is_protocol": True,
                    },
                    {
                        "id": 2,
                        "tid": "T1",
                        "title": "Протокол другой",
                        "link": "/b",
                        "size": 200,
                    },
                ]
            }
        }
        result = _find_protocol_files(tender_data)
        assert len(result) == 1
        assert result[0].file_id == 1

    def test_no_protocols_found(self):
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T1",
                        "title": "Техническое задание",
                        "link": "/a",
                        "size": 100,
                    },
                ]
            }
        }
        result = _find_protocol_files(tender_data)
        assert result == []

    def test_empty_files_by_date(self):
        result = _find_protocol_files({"files_by_date": {}})
        assert result == []

    def test_missing_files_by_date(self):
        result = _find_protocol_files({})
        assert result == []

    def test_multiple_dates(self):
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T1",
                        "title": "x",
                        "link": "/a",
                        "size": 1,
                        "is_protocol": True,
                    },
                ],
                "2024-02-01": [
                    {
                        "id": 2,
                        "tid": "T1",
                        "title": "y",
                        "link": "/b",
                        "size": 2,
                        "is_protocol": True,
                    },
                ],
            }
        }
        result = _find_protocol_files(tender_data)
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# _prioritize_protocols
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrioritizeProtocols:
    def test_docx_before_pdf(self):
        protos = [
            _make_protocol_file(extension="pdf", file_id=1),
            _make_protocol_file(extension="docx", file_id=2),
        ]
        result = _prioritize_protocols(protos)
        assert result[0].extension == "docx"
        assert result[1].extension == "pdf"

    def test_html_before_pdf(self):
        protos = [
            _make_protocol_file(extension="pdf", file_id=1),
            _make_protocol_file(extension="html", file_id=2),
        ]
        result = _prioritize_protocols(protos)
        assert result[0].extension == "html"

    def test_doc_before_html(self):
        protos = [
            _make_protocol_file(extension="html", file_id=1),
            _make_protocol_file(extension="doc", file_id=2),
        ]
        result = _prioritize_protocols(protos)
        assert result[0].extension == "doc"

    def test_unknown_extension_last(self):
        protos = [
            _make_protocol_file(extension="xyz", file_id=1),
            _make_protocol_file(extension="docx", file_id=2),
        ]
        result = _prioritize_protocols(protos)
        assert result[0].extension == "docx"
        assert result[1].extension == "xyz"

    def test_none_extension_last(self):
        protos = [
            _make_protocol_file(extension=None, file_id=1),
            _make_protocol_file(extension="txt", file_id=2),
        ]
        result = _prioritize_protocols(protos)
        assert result[0].extension == "txt"

    def test_same_priority_preserves_order(self):
        protos = [
            _make_protocol_file(extension="htm", file_id=1),
            _make_protocol_file(extension="html", file_id=2),
        ]
        result = _prioritize_protocols(protos)
        # htm and html have same priority (2), order preserved
        assert result[0].file_id == 1
        assert result[1].file_id == 2

    def test_full_priority_chain(self):
        exts = ["pdf", "txt", "html", "doc", "docx"]
        protos = [
            _make_protocol_file(extension=e, file_id=i) for i, e in enumerate(exts)
        ]
        result = _prioritize_protocols(protos)
        assert [p.extension for p in result] == ["docx", "doc", "html", "txt", "pdf"]


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_downloaded_file
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseDownloadedFile:
    def test_html_file_strips_tags(self, tmp_path: Path):
        p = tmp_path / "protocol.html"
        # Text containing a pattern that extract_participants_from_text recognises
        p.write_text(
            "<html><body>Подано <b>5</b> заявок на участие</body></html>",
            encoding="utf-8",
        )
        result, source = _parse_downloaded_file(p)
        assert source == "html"
        assert result.count == 5

    def test_txt_file(self, tmp_path: Path):
        p = tmp_path / "protocol.txt"
        p.write_text("Подано 3 заявки на участие", encoding="utf-8")
        result, source = _parse_downloaded_file(p)
        assert source == "txt"
        assert result.count == 3

    def test_htm_extension(self, tmp_path: Path):
        p = tmp_path / "protocol.htm"
        p.write_text("<p>Подано 2 заявки</p>", encoding="utf-8")
        result, source = _parse_downloaded_file(p)
        assert source == "html"

    def test_unknown_extension(self, tmp_path: Path):
        p = tmp_path / "protocol.xyz"
        p.write_bytes(b"binary stuff")
        result, source = _parse_downloaded_file(p)
        assert "unknown" in source
        assert result.count is None

    def test_doc_with_text_content(self, tmp_path: Path):
        """Old .doc format — attempted as text."""
        p = tmp_path / "protocol.doc"
        # Write enough text (>50 chars) with a recognisable pattern
        content = "A" * 60 + " Подано 4 заявки на участие"
        p.write_text(content, encoding="utf-8")
        result, source = _parse_downloaded_file(p)
        assert source == "doc_text"
        assert result.count == 4

    def test_doc_too_short_falls_back(self, tmp_path: Path):
        """Old .doc with very short text — unsupported fallback."""
        p = tmp_path / "protocol.doc"
        p.write_text("short", encoding="utf-8")
        result, source = _parse_downloaded_file(p)
        assert source == "doc"
        assert result.method == "doc_unsupported"


# ═══════════════════════════════════════════════════════════════════════════════
# _try_get_eis_link (async)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTryGetEisLink:
    """Tests for _try_get_eis_link() async function."""

    @pytest.mark.asyncio
    async def test_finds_eis_link(self) -> None:
        """Returns EIS URL when link element found."""
        page = AsyncMock()
        eis_el = AsyncMock()
        eis_el.get_attribute = AsyncMock(
            return_value="https://zakupki.gov.ru/order/123"
        )
        page.query_selector = AsyncMock(return_value=eis_el)

        from src.parser.html_protocol import _try_get_eis_link

        result = await _try_get_eis_link(page)

        assert result == "https://zakupki.gov.ru/order/123"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_element(self) -> None:
        """Returns None when no EIS link element found."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        from src.parser.html_protocol import _try_get_eis_link

        result = await _try_get_eis_link(page)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_href_is_none(self) -> None:
        """Returns None when element has no href."""
        page = AsyncMock()
        eis_el = AsyncMock()
        eis_el.get_attribute = AsyncMock(return_value=None)
        page.query_selector = AsyncMock(return_value=eis_el)

        from src.parser.html_protocol import _try_get_eis_link

        result = await _try_get_eis_link(page)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        """Returns None when query_selector raises."""
        page = AsyncMock()
        page.query_selector = AsyncMock(side_effect=Exception("DOM error"))

        from src.parser.html_protocol import _try_get_eis_link

        result = await _try_get_eis_link(page)

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# _save_result (async)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSaveResult:
    """Tests for _save_result() async function."""

    @pytest.mark.asyncio
    async def test_delegates_to_upsert_and_commits(self) -> None:
        """Calls upsert_protocol_analysis and commits."""
        conn = AsyncMock()
        result = ProtocolParseResult(
            tender_id="T-1",
            participants_count=3,
            parse_source="html",
            parse_status="success",
            doc_path="/path/doc.html",
            notes="method=direct",
        )

        with patch(
            "src.parser.html_protocol.upsert_protocol_analysis",
            new_callable=AsyncMock,
        ) as mock_upsert:
            from src.parser.html_protocol import _save_result

            await _save_result(conn, result)

        mock_upsert.assert_called_once_with(
            conn,
            tender_id="T-1",
            participants_count=3,
            parse_source="html",
            parse_status="success",
            doc_path="/path/doc.html",
            notes="method=direct",
        )
        conn.commit.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# _download_protocol (async)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDownloadProtocol:
    """Tests for _download_protocol() async function."""

    @pytest.mark.asyncio
    async def test_empty_link_returns_none(self) -> None:
        """Returns None when protocol has no link."""
        page = AsyncMock()
        protocol = _make_protocol_file(link="")

        from src.parser.html_protocol import _download_protocol

        result = await _download_protocol(page, protocol, "T-1", "1234567890")

        assert result is None

    @pytest.mark.asyncio
    async def test_cached_file_returned(self, tmp_path: Path) -> None:
        """Returns existing file without re-downloading."""
        page = AsyncMock()
        protocol = _make_protocol_file(title="Cached", extension="docx", link="/dl/1")

        with patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path):
            # Create the cached file
            download_dir = tmp_path / "inn123" / "T-1"
            download_dir.mkdir(parents=True)
            cached = download_dir / "Cached.docx"
            cached.write_text("cached content")

            from src.parser.html_protocol import _download_protocol

            result = await _download_protocol(page, protocol, "T-1", "inn123")

        assert result is not None
        assert result.name == "Cached.docx"
        # Page should NOT have been used for download
        page.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_fallback_on_download_failure(self, tmp_path: Path) -> None:
        """Falls back to HTTP request when expect_download fails."""
        page = AsyncMock()
        protocol = _make_protocol_file(title="Proto", extension="txt", link="/dl/1")

        # expect_download raises
        page.expect_download = MagicMock(side_effect=Exception("download error"))

        # HTTP fallback succeeds
        mock_response = AsyncMock()
        mock_response.ok = True
        mock_response.body = AsyncMock(return_value=b"file content")
        page.request.get = AsyncMock(return_value=mock_response)

        with patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path):
            from src.parser.html_protocol import _download_protocol

            result = await _download_protocol(page, protocol, "T-1", "inn123")

        assert result is not None
        assert result.read_bytes() == b"file content"

    @pytest.mark.asyncio
    async def test_both_methods_fail_returns_none(self, tmp_path: Path) -> None:
        """Returns None when both expect_download and HTTP fallback fail."""
        page = AsyncMock()
        protocol = _make_protocol_file(title="Proto", extension="txt", link="/dl/1")

        page.expect_download = MagicMock(side_effect=Exception("download error"))
        page.request.get = AsyncMock(side_effect=Exception("HTTP error"))

        with patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path):
            from src.parser.html_protocol import _download_protocol

            result = await _download_protocol(page, protocol, "T-1", "inn123")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_non_ok_returns_none(self, tmp_path: Path) -> None:
        """Returns None when HTTP response is not ok."""
        page = AsyncMock()
        protocol = _make_protocol_file(title="Proto", extension="txt", link="/dl/1")

        page.expect_download = MagicMock(side_effect=Exception("download error"))

        mock_response = AsyncMock()
        mock_response.ok = False
        mock_response.status = 404
        page.request.get = AsyncMock(return_value=mock_response)

        with patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path):
            from src.parser.html_protocol import _download_protocol

            result = await _download_protocol(page, protocol, "T-1", "inn123")

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# _try_eis_protocol (async)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTryEisProtocol:
    """Tests for _try_eis_protocol() async function."""

    @pytest.mark.asyncio
    async def test_protocol_not_found_on_eis(self) -> None:
        """When fallback_get_protocol returns None → no_protocol status."""
        page = AsyncMock()
        conn = AsyncMock()

        with (
            patch(
                "src.parser.html_protocol.fallback_get_protocol",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
        ):
            from src.parser.html_protocol import _try_eis_protocol

            result = await _try_eis_protocol(
                page, "https://eis/tender", "T-1", "inn123", conn
            )

        assert result.parse_status == "no_protocol"
        assert result.parse_source == "eis_not_found"

    @pytest.mark.asyncio
    async def test_protocol_found_and_parsed_successfully(self, tmp_path: Path) -> None:
        """When EIS protocol is found and parsed → success."""
        page = AsyncMock()
        conn = AsyncMock()

        proto_path = tmp_path / "protocol.txt"
        proto_path.write_text("Подано 5 заявок на участие", encoding="utf-8")

        with (
            patch(
                "src.parser.html_protocol.fallback_get_protocol",
                new_callable=AsyncMock,
                return_value=proto_path,
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
            patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path),
            patch("src.parser.html_protocol.KEEP_DOWNLOADED_DOCS", True),
        ):
            from src.parser.html_protocol import _try_eis_protocol

            result = await _try_eis_protocol(
                page, "https://eis/tender", "T-1", "inn123", conn
            )

        assert result.parse_status == "success"
        assert result.participants_count == 5
        assert "eis_" in (result.parse_source or "")

    @pytest.mark.asyncio
    async def test_protocol_found_but_parse_fails(self, tmp_path: Path) -> None:
        """When EIS protocol is found but parsing yields no count → failed."""
        page = AsyncMock()
        conn = AsyncMock()

        proto_path = tmp_path / "protocol.txt"
        proto_path.write_text("No relevant content here at all", encoding="utf-8")

        with (
            patch(
                "src.parser.html_protocol.fallback_get_protocol",
                new_callable=AsyncMock,
                return_value=proto_path,
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
            patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path),
        ):
            from src.parser.html_protocol import _try_eis_protocol

            result = await _try_eis_protocol(
                page, "https://eis/tender", "T-1", "inn123", conn
            )

        assert result.parse_status == "failed"
        assert result.parse_source == "eis_failed"

    @pytest.mark.asyncio
    async def test_exception_returns_failed(self) -> None:
        """When fallback_get_protocol raises → failed with eis_error."""
        page = AsyncMock()
        conn = AsyncMock()

        with (
            patch(
                "src.parser.html_protocol.fallback_get_protocol",
                new_callable=AsyncMock,
                side_effect=Exception("network error"),
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
        ):
            from src.parser.html_protocol import _try_eis_protocol

            result = await _try_eis_protocol(
                page, "https://eis/tender", "T-1", "inn123", conn
            )

        assert result.parse_status == "failed"
        assert result.parse_source == "eis_error"


# ═══════════════════════════════════════════════════════════════════════════════
# analyze_tender_protocol (async)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeTenderProtocol:
    """Tests for analyze_tender_protocol() — full orchestration."""

    @pytest.mark.asyncio
    async def test_no_tenders_data_no_eis_link(self) -> None:
        """When tendersData not found and no EIS link → no_protocol."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<html>no data</html>")
        page.query_selector = AsyncMock(return_value=None)
        conn = AsyncMock()

        with (
            patch("src.parser.html_protocol.safe_goto", new_callable=AsyncMock),
            patch("src.parser.html_protocol.polite_wait", new_callable=AsyncMock),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
        ):
            from src.parser.html_protocol import analyze_tender_protocol

            result = await analyze_tender_protocol(
                page, "T-1", "https://rostender/t/1", "inn123", conn
            )

        assert result.parse_status == "no_protocol"
        assert "tendersData" in (result.notes or "")

    @pytest.mark.asyncio
    async def test_no_tenders_data_with_eis_fallback(self) -> None:
        """When tendersData not found but EIS link exists → delegates to EIS."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<html>no data</html>")

        eis_el = AsyncMock()
        eis_el.get_attribute = AsyncMock(
            return_value="https://zakupki.gov.ru/order/123"
        )
        page.query_selector = AsyncMock(return_value=eis_el)
        conn = AsyncMock()

        eis_result = ProtocolParseResult(
            tender_id="T-1",
            participants_count=2,
            parse_source="eis_txt",
            parse_status="success",
            doc_path=None,
            notes="from EIS",
        )

        with (
            patch("src.parser.html_protocol.safe_goto", new_callable=AsyncMock),
            patch("src.parser.html_protocol.polite_wait", new_callable=AsyncMock),
            patch(
                "src.parser.html_protocol._try_eis_protocol",
                new_callable=AsyncMock,
                return_value=eis_result,
            ) as mock_eis,
        ):
            from src.parser.html_protocol import analyze_tender_protocol

            result = await analyze_tender_protocol(
                page, "T-1", "https://rostender/t/1", "inn123", conn
            )

        assert result.parse_status == "success"
        assert result.participants_count == 2
        mock_eis.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_protocols_in_tenders_data(self) -> None:
        """When tendersData found but no protocol files → no_protocol."""
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {"id": 1, "tid": "T-1", "title": "ТЗ", "link": "/a", "size": 100}
                ]
            }
        }
        page_html = _make_page_html("T-1", tender_data)

        page = AsyncMock()
        page.content = AsyncMock(return_value=page_html)
        page.query_selector = AsyncMock(return_value=None)  # no EIS link
        conn = AsyncMock()

        with (
            patch("src.parser.html_protocol.safe_goto", new_callable=AsyncMock),
            patch("src.parser.html_protocol.polite_wait", new_callable=AsyncMock),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
        ):
            from src.parser.html_protocol import analyze_tender_protocol

            result = await analyze_tender_protocol(
                page, "T-1", "https://rostender/t/1", "inn123", conn
            )

        assert result.parse_status == "no_protocol"

    @pytest.mark.asyncio
    async def test_protocol_downloaded_and_parsed_success(self, tmp_path: Path) -> None:
        """Full success path: tendersData → protocol found → downloaded → parsed."""
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T-1",
                        "title": "Протокол итогов",
                        "link": "/dl/1",
                        "size": 100,
                        "is_protocol": True,
                        "ext": "txt",
                    }
                ]
            }
        }
        page_html = _make_page_html("T-1", tender_data)

        page = AsyncMock()
        page.content = AsyncMock(return_value=page_html)
        conn = AsyncMock()

        # Create a file that will be "downloaded"
        download_dir = tmp_path / "inn123" / "T-1"
        download_dir.mkdir(parents=True)
        proto_file = download_dir / "Протокол итогов.txt"
        proto_file.write_text("Подано 4 заявки на участие", encoding="utf-8")

        with (
            patch("src.parser.html_protocol.safe_goto", new_callable=AsyncMock),
            patch("src.parser.html_protocol.polite_wait", new_callable=AsyncMock),
            patch(
                "src.parser.html_protocol._download_protocol",
                new_callable=AsyncMock,
                return_value=proto_file,
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
            patch("src.parser.html_protocol.DOWNLOADS_DIR", tmp_path),
            patch("src.parser.html_protocol.KEEP_DOWNLOADED_DOCS", True),
        ):
            from src.parser.html_protocol import analyze_tender_protocol

            result = await analyze_tender_protocol(
                page, "T-1", "https://rostender/t/1", "inn123", conn
            )

        assert result.parse_status == "success"
        assert result.participants_count == 4
        assert result.parse_source == "txt"

    @pytest.mark.asyncio
    async def test_download_fails_tries_next_protocol(self) -> None:
        """When download fails for first protocol, tries next one."""
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T-1",
                        "title": "Протокол 1",
                        "link": "/dl/1",
                        "size": 100,
                        "is_protocol": True,
                        "ext": "docx",
                    },
                    {
                        "id": 2,
                        "tid": "T-1",
                        "title": "Протокол 2",
                        "link": "/dl/2",
                        "size": 200,
                        "is_protocol": True,
                        "ext": "txt",
                    },
                ]
            }
        }
        page_html = _make_page_html("T-1", tender_data)

        page = AsyncMock()
        page.content = AsyncMock(return_value=page_html)
        conn = AsyncMock()

        call_count = 0

        async def mock_download(pg, protocol, tid, inn):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # First download fails
            # Second returns a file
            return Path("/fake/path.txt")

        with (
            patch("src.parser.html_protocol.safe_goto", new_callable=AsyncMock),
            patch("src.parser.html_protocol.polite_wait", new_callable=AsyncMock),
            patch(
                "src.parser.html_protocol._download_protocol",
                new_callable=AsyncMock,
                side_effect=mock_download,
            ),
            patch(
                "src.parser.html_protocol._parse_downloaded_file",
                return_value=(
                    MagicMock(count=3, method="direct", confidence="high"),
                    "txt",
                ),
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
            patch("src.parser.html_protocol.DOWNLOADS_DIR", Path("/fake")),
            patch("src.parser.html_protocol.KEEP_DOWNLOADED_DOCS", False),
        ):
            from src.parser.html_protocol import analyze_tender_protocol

            result = await analyze_tender_protocol(
                page, "T-1", "https://rostender/t/1", "inn123", conn
            )

        assert result.parse_status == "success"
        assert result.participants_count == 3
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_protocols_fail_returns_failed(self) -> None:
        """When all protocol downloads fail → failed status."""
        tender_data = {
            "files_by_date": {
                "2024-01-01": [
                    {
                        "id": 1,
                        "tid": "T-1",
                        "title": "Протокол",
                        "link": "/dl/1",
                        "size": 100,
                        "is_protocol": True,
                        "ext": "docx",
                    },
                ]
            }
        }
        page_html = _make_page_html("T-1", tender_data)

        page = AsyncMock()
        page.content = AsyncMock(return_value=page_html)
        page.query_selector = AsyncMock(return_value=None)  # no EIS
        conn = AsyncMock()

        with (
            patch("src.parser.html_protocol.safe_goto", new_callable=AsyncMock),
            patch("src.parser.html_protocol.polite_wait", new_callable=AsyncMock),
            patch(
                "src.parser.html_protocol._download_protocol",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.parser.html_protocol.upsert_protocol_analysis",
                new_callable=AsyncMock,
            ),
        ):
            from src.parser.html_protocol import analyze_tender_protocol

            result = await analyze_tender_protocol(
                page, "T-1", "https://rostender/t/1", "inn123", conn
            )

        assert result.parse_status == "failed"
