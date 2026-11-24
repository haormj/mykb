---
type: concept
title: OKF 知识存储
description: OKF bundle 的两级布局、概念模型与 frontmatter 字段、序列化往返、一致性校验，以及 git、分支与 Git LFS 如何承载知识库内容。
tags: [okf, bundle, markdown, frontmatter, git, lfs, storage]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-7aadd6d3aee18b8ba7b0c4bb
    resource: repo://mykb/cli.py
  - id: openwiki-source-322ecf6ee28e880192405c21
    resource: repo://mykb/importing/concepts.py
  - id: openwiki-source-91a18e39cc4183c866d2a60b
    resource: repo://mykb/kb/gitops.py
  - id: openwiki-source-64f1fc6e907f310d1d97d3c6
    resource: repo://mykb/okf/bundle.py
  - id: openwiki-source-4c2fbad36351b6670606b9ea
    resource: repo://mykb/okf/model.py
  - id: openwiki-source-f3ec87b2651bef3c59d028f4
    resource: repo://mykb/okf/validate.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# OKF 知识存储

每个知识库的内容是一个独立的 git 仓库，其目录结构遵循 OKF（Open Knowledge Format）bundle：一个由 Markdown 文件组成的目录树，每个文件带 YAML frontmatter。`mykb/okf/bundle.py` 负责布局与读写，`mykb/okf/model.py` 负责单个概念的解析与序列化，`mykb/okf/validate.py` 负责一致性校验。git 与 LFS 细节由 `mykb/kb/gitops.py` 承担。

## 两级布局

bundle 固定分为 `raw/` 和 `knowledge/` 两级（`LEVELS`），另有若干保留文件名：

- `raw/`：源数据，即转换后的文档概念，由导入流程写入。
- `knowledge/`：业务知识，由 AI 提取与人工评审后合入。
- `index.md`、`log.md`：保留文件名，不参与概念枚举（`RESERVED_FILENAMES`）。
- 根目录 `index.md`：bundle 元数据，含 `okf_version`（默认 `0.3`）、`title`、可选 `description`、`version`（`mykb/okf/bundle.py:64`）。
- 每个 level 目录下也各有一个 `index.md` 占位。

`ensure_layout` 幂等地创建两级目录、level 索引和根索引（`mykb/okf/bundle.py:55`）。概念 id 由相对路径去掉 `.md` 得到，例如 `knowledge/topics/ltv` 对应 `knowledge/topics/ltv.md`（`mykb/okf/bundle.py:97`）。

## 概念模型与 frontmatter

一个概念就是“YAML frontmatter + markdown 正文”。模型层只要求 frontmatter 是 YAML 映射，且 `type` 是唯一必填字段；未知字段在往返时保留，因为 OKF 规范要求消费者保留不理解的扩展字段（`mykb/okf/model.py:1`）。

`Concept` 提供若干便捷属性：`type`、`title`、`status`、`resource`、`stale_after`、`superseded_by`、`sources`、`verified`、`generated`（`mykb/okf/model.py:92`）。其中：

- `sources` 与 `verified` 都会归一化为列表，`source_ids()` 从每个来源条目取 `id` 或 `resource`（`mykb/okf/model.py:130`）。
- `is_verified_stable()` 是检索可见性的判定：`status == "stable"` 且 `verified` 非空（`mykb/okf/model.py:145`）。

源数据概念由 `build_source_concept` 生成，frontmatter 记录完整的来源溯源：`type`、`title`、`resource`、`generated`、`status: draft`、`tags`、`x-connector`、`x-import-task`、`x-source-format`、`x-original-name`、`x-original-sha256`、`x-original-size`、`x-parsed-by`，转换告警写入 `x-warnings`（`mykb/importing/concepts.py:9`）。`resource` 只是逻辑来源标识，不承诺可回取。

## 序列化与幂等往返

- `parse` 要求文档以 `---` 开始并有闭合 `---`，将 frontmatter 解析为字典、其余为正文；非法 YAML 或非映射会抛 `FrontmatterError`（`mykb/okf/model.py:45`）。
- `serialize` 使用自定义 `SafeDumper` 保留键顺序并支持 Unicode，时间类型统一渲染为 ISO-8601 字符串，避免往返后类型漂移（`mykb/okf/model.py:28`）。
- `_normalize` 在解析时把 datetime/date 递归转成 ISO 字符串，确保写回时仍是纯字符串（`mykb/okf/model.py:38`）。

## 资产与安全边界

- 图片等派生资产写在概念同级的 `<concept>.assets/` 目录，链接相对概念文件形如 `foo.assets/img-1.png`（`mykb/okf/bundle.py:122`）。
- `asset_dir_for` 解析路径后会校验它仍在 bundle 根内，防止 `..` 逃逸（`mykb/okf/bundle.py:128`）。
- `write_assets` 拒绝空名、`.`、`..`、含路径分隔符或反斜杠的资产名（`mykb/okf/bundle.py:146`）。
- `read_asset` 额外检查：目标必须是 `.assets` 目录的直接子文件，且内容不能是未拉取的 Git LFS 指针（以 `version https://git-lfs` 开头），否则视为缺失（`mykb/okf/bundle.py:178`）。API 层据此把缺失资产映射为 404。

## 校验

`validate_bundle` 遍历两级目录下所有非保留 `.md` 文件，要求每个文件有可解析的 frontmatter 映射和非空的 `type`，收集成 `ValidationIssue` 列表（`mykb/okf/validate.py:21`）。CLI 的 `mykb validate <root>` 用空列表判定通过（`mykb/cli.py:25`）。注意该校验只检查格式合规，不检查引用断链、重复实体等语义问题——那些在提取 harness 写盘前完成。

## git 与 Git LFS 承载

`mykb/kb/gitops.py` 把 bundle 目录当作一个 git 仓库管理：

- 提交作者固定为 `mykb-agent <agent@mykb.local>`，通过 `-c user.name/user.email` 注入（`mykb/kb/gitops.py:12`）。
- 新建仓库用 `git init -b main`，初始化布局后 `commit_all` 提交 `chore: init bundle`（`mykb/kb/gitops.py:107`）。
- 克隆远程时先克隆，按需切换/新建分支，再确保布局与 LFS，最后推送（`mykb/kb/gitops.py:119`）。
- `ensure_lfs` 在没有 `git-lfs` 二进制时直接跳过：因为写入 LFS filter 属性会让二进制 `git add` 失败，而纯 Markdown 导入必须仍可用；有 LFS 时写入 png/jpg/jpeg/gif/webp 的 `.gitattributes` 并执行 `git lfs install --local`（`mykb/kb/gitops.py:68`）。
- 绑定 HTTPS 远程前会探测其 LFS 能力，不支持则拒绝绑定（`mykb/kb/gitops.py:94`）。

分支约定：主干为 `main`；每份待审文档一个 `change/doc-<slug>` 分支，`merge_branch` 用 `--no-ff` 合并并在合并后可由 `delete_branch` 清理（`mykb/kb/gitops.py:166`）。`changed_files_vs` 与 `diff_text` 以三点 `base...branch` 计算评审差异（`mykb/kb/gitops.py:183`）。

## 备份注意

由于图片由 LFS 管理，备份知识库时必须包含 `.git/lfs/objects` 或依赖远程 LFS 对象，否则恢复后图片只剩指针；本地空间可用 `git lfs prune` 清理未被引用的对象。这是 README 中明确记录、且与 `read_asset` 的 LFS 指针检测相互印证的操作约束。

## 相关测试

`tests/test_okf_model.py`、`tests/test_okf_bundle.py`、`tests/test_okf_validate.py` 覆盖解析/序列化往返、布局与 id 解析、资产路径安全、校验失败场景；`tests/test_git_lfs.py`、`tests/test_gitops.py` 覆盖 LFS 与 git 操作。
