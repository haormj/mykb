from __future__ import annotations

import base64
import hashlib
import threading
import time
from pathlib import Path

import httpx
import pytest

from mykb.config import ConfigError, Settings, load_settings
from mykb.conversion.assets import prepare_assets, rewrite_asset_links
from mykb.conversion.base import (
    Asset,
    ConversionAuthError,
    ConversionError,
    ConversionLimitError,
    ConversionNotConfiguredError,
    ConversionResult,
    ConversionUnavailableError,
    RawDocument,
    UnsupportedFormatError,
)
from mykb.conversion.mineru import MineruHttpConverter
from mykb.conversion.passthrough import MarkdownPassthroughConverter
from mykb.conversion.registry import select_converter
from mykb.conversion.service import ConverterService
from mykb.okf.bundle import Bundle

PNG = b"\x89PNG\r\n\x1a\nfake"
JPEG = b"\xff\xd8\xff\xe0fake"


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "database_url": "sqlite://",
        "jwt_secret": "secret",
        "secret_key": "secret",
        "kb_root": tmp_path,
    }
    values.update(overrides)
    return Settings(**values)


def _docx(data: bytes = b"PK\x03\x04binary", name: str = "note.docx") -> RawDocument:
    return RawDocument(
        key=name,
        name=name,
        data=data,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        suffix=".docx",
    )


class StubConverter:
    name = "stub"

    def __init__(self, result: ConversionResult | None = None, delay: float = 0.0) -> None:
        self.calls = 0
        self.result = result or ConversionResult(markdown="# Hi", producer="stub")
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def supports(self, suffix: str, mime: str) -> bool:
        return suffix == ".docx"

    def convert(self, document: RawDocument) -> ConversionResult:
        self.calls += 1
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return self.result
        finally:
            with self._guard:
                self.active -= 1


def test_parser_settings_defaults_and_validation(tmp_path):
    base = {
        "DATABASE_URL": "sqlite://",
        "JWT_SECRET": "secret",
        "MYKB_SECRET_KEY": "secret",
        "MYKB_KB_ROOT": str(tmp_path),
    }
    settings = load_settings(base)
    assert settings.parser_url is None
    assert settings.parser_timeout == 60.0
    assert settings.parser_tier == "flash"
    assert settings.parser_concurrency == 2
    assert settings.parser_token is None

    configured = load_settings(
        {
            **base,
            "MYKB_PARSER_URL": "http://parser:8080/v1/file_parse",
            "MYKB_PARSER_TIMEOUT": "12.5",
            "MYKB_PARSER_TIER": "basic",
            "MYKB_PARSER_CONCURRENCY": "3",
            "MYKB_PARSER_TOKEN": "token",
            "MYKB_CONVERSION_MAX_ASSETS": "4",
            "MYKB_CONVERSION_MAX_ASSET_BYTES": "1024",
            "MYKB_CONVERSION_MAX_MARKDOWN_BYTES": "2048",
            "MYKB_KB_ASSET_QUOTA_BYTES": "4096",
        }
    )
    assert configured.parser_url == "http://parser:8080/v1/file_parse"
    assert configured.parser_timeout == 12.5
    assert configured.parser_tier == "basic"
    assert configured.parser_concurrency == 3
    assert configured.parser_token == "token"
    assert configured.conversion_max_assets == 4
    assert configured.kb_asset_quota_bytes == 4096

    with pytest.raises(ConfigError):
        load_settings({**base, "MYKB_PARSER_TIMEOUT": "soon"})
    with pytest.raises(ConfigError):
        load_settings({**base, "MYKB_PARSER_CONCURRENCY": "0"})


def test_passthrough_preserves_frontmatter_and_rejects_unknown():
    converter = MarkdownPassthroughConverter()
    document = RawDocument(
        key="note.md",
        name="note.md",
        data=b"---\ntitle: Title\n---\nbody",
        mime="text/markdown",
        suffix=".md",
    )
    result = converter.convert(document)
    assert result.title == "Title"
    assert result.markdown == "body"
    assert result.frontmatter == {"title": "Title"}
    assert result.producer == "passthrough"

    with pytest.raises(UnsupportedFormatError):
        select_converter([converter], ".pdf", "application/pdf")


def test_mineru_success_and_request_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://parser/v1/file_parse"
        assert request.headers["authorization"] == "Bearer secret"
        assert request.headers["content-type"].startswith("multipart/form-data")
        return httpx.Response(
            200,
            json={
                "markdown": "# Doc\n\n![img](img-1.png)",
                "title": "Doc",
                "parser_version": "4.2.0",
                "warnings": ["layout simplified"],
                "assets": [
                    {
                        "name": "img-1.png",
                        "content_base64": base64.b64encode(PNG).decode("ascii"),
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    converter = MineruHttpConverter(
        "http://parser/v1/file_parse", token="secret", client=client
    )
    result = converter.convert(_docx())
    assert result.title == "Doc"
    assert result.producer == "mineru@4.2.0"
    assert result.warnings == ["layout simplified"]
    assert result.assets == [Asset(name="img-1.png", data=PNG, source_name="img-1.png")]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ConversionAuthError),
        (403, ConversionAuthError),
        (500, ConversionUnavailableError),
        (422, ConversionError),
    ],
)
def test_mineru_http_errors(status, expected):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, text="no"))
    )
    converter = MineruHttpConverter("http://parser", client=client)
    with pytest.raises(expected):
        converter.convert(_docx())


def test_mineru_network_and_payload_errors():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=_request)

    converter = MineruHttpConverter(
        "http://parser", client=httpx.Client(transport=httpx.MockTransport(boom))
    )
    with pytest.raises(ConversionUnavailableError):
        converter.convert(_docx())

    not_json = MineruHttpConverter(
        "http://parser",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="nope"))
        ),
    )
    with pytest.raises(ConversionUnavailableError):
        not_json.convert(_docx())


def test_mineru_requires_configuration(tmp_path):
    converter = MineruHttpConverter(None)
    with pytest.raises(ConversionNotConfiguredError):
        converter.convert(_docx())

    service = ConverterService(_settings(tmp_path))
    with pytest.raises(ConversionNotConfiguredError):
        service.convert(_docx())


def test_cache_skips_repeated_conversion(tmp_path):
    stub = StubConverter()
    service = ConverterService(_settings(tmp_path), converters=[stub])
    first = service.convert(_docx())
    second = service.convert(_docx())
    assert stub.calls == 1
    assert first.markdown == second.markdown

    service.convert(_docx(b"PK\x03\x04different"))
    assert stub.calls == 2
    assert (tmp_path / ".cache" / "parse").exists()


def test_conversion_limits(tmp_path):
    too_long = StubConverter(ConversionResult(markdown="x" * 64))
    with pytest.raises(ConversionLimitError):
        ConverterService(
            _settings(tmp_path, conversion_max_markdown_bytes=10),
            converters=[too_long],
        ).convert(_docx())

    many = StubConverter(
        ConversionResult(
            markdown="ok",
            assets=[Asset("a.png", PNG), Asset("b.png", JPEG)],
        )
    )
    with pytest.raises(ConversionLimitError):
        ConverterService(
            _settings(tmp_path, conversion_max_assets=1), converters=[many]
        ).convert(_docx())

    big = StubConverter(
        ConversionResult(markdown="ok", assets=[Asset("a.png", PNG * 10)])
    )
    with pytest.raises(ConversionLimitError):
        ConverterService(
            _settings(tmp_path, conversion_max_asset_bytes=5), converters=[big]
        ).convert(_docx())


def test_prepare_assets_names_and_filters():
    assets, warnings = prepare_assets(
        [
            Asset(name="../../evil.png", data=PNG, source_name="evil.png"),
            Asset(name="diagram.svg", data=b"<svg/>", source_name="diagram.svg"),
            Asset(name="photo.jpeg", data=JPEG, source_name="photo.jpeg"),
        ],
        max_assets=10,
        max_asset_bytes=1024,
    )
    assert [asset.name for asset in assets] == [
        f"001-{hashlib.sha256(PNG).hexdigest()[:8]}.png",
        f"002-{hashlib.sha256(JPEG).hexdigest()[:8]}.jpeg",
    ]
    assert warnings == ["dropped non-bitmap asset: diagram.svg"]
    assert all("/" not in asset.name for asset in assets)


def test_rewrite_asset_links():
    assets = [Asset(name="001-abc.png", data=PNG, source_name="img-1.png")]
    markdown = "![a](img-1.png) ![b](other.png) ![c](img-1.png \"title\")"
    rewritten = rewrite_asset_links(markdown, assets, "note")
    assert "![a](note.assets/001-abc.png)" in rewritten
    assert "![b](other.png)" in rewritten
    assert "![c](note.assets/001-abc.png \"title\")" in rewritten


def test_concurrency_semaphore(tmp_path):
    stub = StubConverter(delay=0.05)
    service = ConverterService(
        _settings(tmp_path, parser_concurrency=2), converters=[stub]
    )
    threads = [
        threading.Thread(target=service.convert, args=(_docx(b"PK\x03\x04" + bytes([i])),))
        for i in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert stub.calls == 6
    assert stub.max_active <= 2


def test_bundle_assets_are_written_and_not_concepts(tmp_path):
    bundle = Bundle(tmp_path / "kb")
    bundle.ensure_layout()
    links = bundle.write_assets("raw", "upload/note.md", [Asset("001-abc.png", PNG)])
    assert links == ["note.assets/001-abc.png"]
    assert (tmp_path / "kb" / "raw" / "upload" / "note.assets" / "001-abc.png").read_bytes() == PNG
    assert bundle.all_concept_ids() == []
    assert bundle.asset_bytes() == len(PNG)

    bundle.remove_assets("raw", "upload/note.md")
    assert bundle.asset_bytes() == 0
