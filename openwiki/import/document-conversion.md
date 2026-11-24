---
type: concept
title: 文档转换与资产处理
description: mykb 将上传文档转成 markdown 的转换层：Markdown 直通、docx 经内部 MinerU sidecar、按后缀路由、输出与资产限额、确定性命名的图片资产、链接改写、转换缓存与 Git LFS 存储。
tags: [conversion, docx, markdown, assets, sidecar, mineru, lfs]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-48aeb34c6b9f9399d4a80b4c
    resource: repo://mykb/conversion/assets.py
  - id: openwiki-source-c0c5611179789fbd7bd801e6
    resource: repo://mykb/conversion/base.py
  - id: openwiki-source-4dbce81e434032294d35bfea
    resource: repo://mykb/conversion/mineru.py
  - id: openwiki-source-e523daf52f78be3ac4a3f184
    resource: repo://mykb/conversion/passthrough.py
  - id: openwiki-source-f5095ea9e5a4bbd1e177438e
    resource: repo://mykb/conversion/registry.py
  - id: openwiki-source-88fa7f853ea1b7332191c0cc
    resource: repo://mykb/conversion/service.py
  - id: openwiki-source-10133604e05abac5ade9afe0
    resource: repo://mykb/importing/service.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 文档转换与资产处理

转换层位于“连接器同步出原始字节”之后、“包装成 OKF 概念”之前：它把一份原始文档变成 markdown（可选标题、frontmatter、图片资产、告警），供后续导入流程写入 raw 概念。支持范围是 Markdown 直通与 `.docx` 经内部 sidecar 转换；v1 不支持 `.pdf` 与旧版 `.doc`。

## 支持的格式与路由

- `SUPPORTED_SUFFIXES = {".md", ".markdown", ".docx"}`，`MARKDOWN_SUFFIXES = {".md", ".markdown"}`，`ALLOWED_ASSET_SUFFIXES = {".png",".jpg",".jpeg",".gif",".webp"}`（`mykb/conversion/base.py:13`）。
- 转换器通过 `register_converter` 注册，`select_converter` 按顺序返回第一个 `supports(suffix, mime)` 为真的提供者（`mykb/conversion/registry.py:26`）。默认顺序是 Markdown 直通在前、MinerU 在后（`mykb/conversion/registry.py:20`）。新增格式只需实现 `DocumentConverter` 协议并注册，无需改导入流水线。

`DocumentConverter` 协议要求 `name`、`supports(suffix, mime)`、`convert(document) -> ConversionResult`（`mykb/conversion/base.py:86`）。

## Markdown 直通

`MarkdownPassthroughConverter` 把上传的 `.md/.markdown` 视为“已转换”（`mykb/conversion/passthrough.py:16`）：

- 必须是 UTF-8 解码，否则抛 `ConversionError`；
- 若文本带合法 frontmatter，则剥离出来放进结果的 `frontmatter`，正文作为 markdown；否则整体作为正文；
- 标题优先取 frontmatter 的 `title`，否则取文件名主干；
- `producer` 为 `passthrough`。

直通转换不经过缓存、不占用解析并发信号量。

## docx 经内部 sidecar（MinerU）

`MineruHttpConverter` 只接受 `.docx` 或对应 MIME（`mykb/conversion/mineru.py:36`）。请求与响应协议：

- 请求：`POST <MYKB_PARSER_URL>`，`multipart/form-data`，字段 `file`（原始文档）与 `tier`（解析档位，来自 `MYKB_PARSER_TIER`，默认 `flash`）；若配置了 `MYKB_PARSER_TOKEN` 则附 `Authorization: Bearer`（`mykb/conversion/mineru.py:48`）。
- 响应 JSON：`markdown`（必需字符串）、可选 `title`、`parser_version`/`version`、`warnings`、`assets`（每项 `{name, content_base64, source_name?}`）。

错误映射（`mykb/conversion/mineru.py:71`）：

| 情况 | 异常 | 影响 |
| --- | --- | --- |
| 未配置 `MYKB_PARSER_URL` | `ConversionNotConfiguredError` | 该条目失败 |
| 超时/网络错误 | `ConversionUnavailableError` | 整个任务 `failed` 可重试 |
| 401/403 | `ConversionAuthError`（`Unavailable` 子类） | 整个任务 `failed` |
| 5xx | `ConversionUnavailableError` | 整个任务 `failed` |
| 其它 4xx | `ConversionError` | 该条目失败，计数并继续 |
| 非法 JSON / 缺 markdown / 非法资产 base64 | `ConversionUnavailableError` 或 `ConversionError` | 视情况整任务或单条目失败 |

`producer` 记录为 `mineru@<parser_version>`（无版本时 `mineru`），最终写入源概念的 `x-parsed-by`，用于追踪解析版本。

sidecar 的部署约束（README）：只允许部署在内网、容器不得出网、显式禁用 MinerU 的 `--remote`、模型与依赖预置镜像、固定镜像 tag、设置资源与进程限额，并让 `MYKB_PARSER_CONCURRENCY` 不超过 sidecar 实际并发能力。

## 转换服务：限额、并发与缓存

`ConverterService` 是转换的统一入口（`mykb/conversion/service.py:24`）：

1. 选择提供者；若为 passthrough 直接返回（不校验、不缓存）。
2. 以文档内容的 SHA-256 为 key 查 `MYKB_KB_ROOT/.cache/parse/<digest>/result.json` 缓存，命中则反序列化返回（`mykb/conversion/service.py:50`）。
3. 否则在 `Semaphore(parser_concurrency)` 限流下调用提供者（`mykb/conversion/service.py:49`）。
4. 校验并归一化输出后写缓存（缓存写失败被忽略，不影响主流程）。

`_validate` 强制两类限制（`mykb/conversion/service.py:56`）：

- markdown UTF-8 字节数不得超过 `MYKB_CONVERSION_MAX_MARKDOWN_BYTES`（默认 10 MiB），否则 `ConversionLimitError`；
- 资产经 `prepare_assets` 处理，单文档图片数超过 `MYKB_CONVERSION_MAX_ASSETS`（默认 100）或资产总大小超过 `MYKB_CONVERSION_MAX_ASSET_BYTES`（默认 20 MiB）时抛 `ConversionLimitError`。

缓存只对需要外部解析的格式生效，且以内容摘要为键，因此同一文件重复导入不会重复调用 sidecar。

## 资产归一化与安全

`prepare_assets` 刻意不信任解析器给出的文件名（`mykb/conversion/assets.py:13`）：

- 只保留位图后缀（png/jpg/jpeg/gif/webp），其它资产被丢弃并记一条 `dropped non-bitmap asset` 告警；
- 资产名重写为 `<序号>-<内容前8位摘要><后缀>`，例如 `001-ab12cd34.png`，既确定性又避免路径穿越和不稳定的解析器命名；
- 累计资产大小超限则抛 `ConversionLimitError`。

因为文件名从不取自解析器，路径穿越在源头就被消除。

## 链接改写

`rewrite_asset_links` 用正则匹配 markdown 的 `](target)` 形式，把引用资产名或原始 `source_name` 的链接改写为 `<concept_alias>.assets/<new_name>`（`mykb/conversion/assets.py:37`）。`concept_alias` 是概念相对路径的文件名主干（`mykb/conversion/service.py:104`），因此图片最终落在概念同级的 `.assets/` 目录，与 OKF 存储约定一致。详见 [OKF 知识存储](../architecture/knowledge-storage.md)。

## 从转换到入库的衔接

导入流程在 `_stage_document` 中串联转换与暂存（`mykb/importing/service.py:186`）：

1. `converter.convert(document)` 得到结果；
2. `rewrite_asset_links` 改写资产链接；
3. 若有资产但宿主没有 `git-lfs`，抛 `ConversionUnavailableError`（图片无法落库）；
4. 若写入资产会超过 `MYKB_KB_ASSET_QUOTA_BYTES`（默认 512 MiB/库），抛 `ConversionLimitError`；
5. 用结果构建源概念（记录 `x-parsed-by` 等溯源），比较 `x-original-sha256` 判断是否跳过，否则生成 `add`/`modify` 提取项并把概念与资产暂存到 `.pending/<item_id>`。

资产实际写入 git 是在提取 worker 构建文档级 MR 时完成，由 `Bundle.write_assets` 与 Git LFS 承载；导入阶段只在仓库外暂存。

## 失败语义

- 单条转换失败（`ConversionError`/`ConversionLimitError`）只让该条目计数失败，任务可以 `partial` 或 `failed`（当没有成功项且全部失败时 `failed`）。
- 转换服务不可达或鉴权失败（`ConversionUnavailableError` 及其子类）是**致命**的：立即停止循环、把任务标 `failed`，并清理已排队但未处理项的暂存，避免把半成品推入评审。
- 未配置解析服务时 docx 条目得到 `ConversionNotConfiguredError`，仅在只含 Markdown 的部署中可正常使用。

## 代表测试

`tests/test_conversion.py` 覆盖直通解析、frontmatter 保留、docx sidecar 的错误映射、资产重命名与丢弃、限额、链接改写与缓存；`tests/test_document_import.py` 与 `tests/test_e2e.py` 覆盖转换在导入任务中的整体行为。
