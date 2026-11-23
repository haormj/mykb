# Tasks

## 1. 接入验证（先证伪风险）

- [ ] 1.1 启动内部 MinerU sidecar 并验证 docx 解析：模型预置在镜像内、禁用 `--remote`、容器无出网；用样例 `.docx` 调用后记录端点、版本与返回的 markdown/图片结构。验证方式：保存一次真实调用的请求/响应样例到测试夹具。
- [x] 1.2 本地验证 Git LFS 链路：初始化知识库后确认 `.gitattributes` 与 `filter.lfs` 配置，导入含图片的 docx 后确认 `git lfs ls-files` 列出资产、`git show HEAD:<asset>` 为 LFS 指针。验证方式：`tests/test_document_import.py::test_docx_assets_are_committed_as_lfs_pointers` 通过。
- [ ] 1.3 远程验证 Git LFS 链路（待目标环境）：在内部 Git 平台 push 含图片的知识库并克隆还原。验证方式：远端克隆后 `git lfs ls-files` 与图片内容完整；若 `oauth2:<token>@host` 不被 LFS 接受，记录所需配置。

## 2. 转换 provider 与配置

- [x] 2.1 在 `mykb/config.py` 增加 `MYKB_PARSER_URL`、`MYKB_PARSER_TIMEOUT`、`MYKB_PARSER_TIER`、`MYKB_PARSER_CONCURRENCY`、`MYKB_PARSER_TOKEN` 的读取与默认值。验证方式：配置单测覆盖空 URL、非法数值与缺省值。
- [x] 2.2 新增转换层类型与注册表（`RawDocument`、`Asset`、`ConversionResult`、`DocumentConverter`、按扩展名/MIME 路由），并实现 `.md`/`.markdown` 的 passthrough。验证方式：单测断言 passthrough 保留原 frontmatter、未知类型不被 passthrough 接受。
- [x] 2.3 实现 MinerU HTTP provider：单条请求、超时、错误分类（格式失败/服务不可达/鉴权失败）、读取并记录解析版本、把返回图片规整为 `Asset`。验证方式：用 1.1 的夹具做无网络 mock 单测，覆盖成功与三类失败。
- [x] 2.4 实现按 `x-original-sha256` 的解析结果缓存（派生结果缓存于 `MYKB_KB_ROOT/.cache/parse/<sha256>/`）。验证方式：单测断言相同内容第二次转换不再调用 provider、不同内容会重新转换。

## 3. 上传入口改造

- [x] 3.1 更新 `mykb/importing/service.py` 白名单为 `.md/.markdown/.docx/.zip`，zip 解压保留 docx 条目并继续阻断路径穿越。验证方式：单测覆盖 docx 通过、pdf/doc/exe 拒绝、zip 混合条目与 `../` 攻击。
- [x] 3.2 调整连接器：`sync` 产出原始文件字节与 MIME，不再对 docx 调用 `read_text`；上传连接器复用该行为。验证方式：单测用二进制 docx 字节断言 sync 不抛解码错误且保留 key/name。
- [x] 3.3 更新前端 `DocumentsTab.tsx` 的 `accept` 与提示文案为 Markdown、docx、zip。验证方式：前端构建通过，人工检查上传控件接受 `.docx`。

## 4. 资产写入与 Git LFS

- [x] 4.1 实现资产确定性命名（序号 + 内容 hash + 白名单位图扩展名）、路径穿越防护与单文档资产数量/大小限额。验证方式：单测覆盖重名、非法文件名、超限拒绝、非位图跳过。
- [x] 4.2 在 `mykb/okf/bundle.py` 增加资产写入能力，写入 `<concept>.assets/` 并返回可写进 markdown 的相对路径；确保概念枚举仍只扫 `*.md`。验证方式：单测断言资产落盘、`iter_concepts` 不返回资产。
- [x] 4.3 在仓库初始化/补布局路径写入覆盖图片扩展名的 `.gitattributes` 并执行 `git lfs install --local`。验证方式：新建知识库后断言文件内容与 `.git/config` 中 LFS 配置存在。
- [x] 4.4 增加 `git-lfs` 可执行检测与 `bind_remote` 远程 LFS 能力探测；缺失/不支持时给出明确错误。验证方式：单测 mock 探测结果，覆盖支持、不支持、命令缺失三条路径。
- [x] 4.5 实现每库资产配额检查，超限时按条目失败且不写入。验证方式：单测构造超额资产断言失败且既有内容不变。
- [x] 4.6 在 README 更新导入说明、LFS 前置条件、备份口径与 `git lfs prune` 运维说明。验证方式：按文档命令可完成一次带资产的导入与备份恢复演练。

## 5. 任务编排与来源标记

- [x] 5.1 重构 `run_import_task` 执行顺序为「读取原始文件 → 转换 → 校验 → 写概念/资产 → 提交 git」，转换在写库前完成。验证方式：单测断言失败条目未产生概念或资产。
- [x] 5.2 落实失败语义：单条失败计入 `failed` 且任务 `partial`；sidecar 未配置或不可达任务 `failed` 可重试；不写半成品。验证方式：单测覆盖三种分支与计数。
- [x] 5.3 写入 `x-source-format`、`x-original-name`、`x-original-sha256`、`x-original-size`、`x-parsed-by`，并保持 `x-import-task`；确认 `resource` 为逻辑标识。验证方式：单测断言 docx 与 md 两类概念的 frontmatter 字段齐全。
- [x] 5.4 确保终态删除上传临时目录与原始文档（成功、失败、取消），仓库中不出现原件。验证方式：集成测试在任务结束后断言临时目录不存在、`git ls-files` 无原始 docx/zip。
- [x] 5.5 用信号量按 `MYKB_PARSER_CONCURRENCY` 限制并发转换，超时后按错误归类。验证方式：并发单测断言同时进行的 provider 调用数不超过配置值。

## 6. 集成验证

- [x] 6.1 端到端测试：同一任务上传 `.md`、`.docx` 与混合 zip，断言任务计数、raw 概念、资产相对链接、LFS 指针与原件不落库。验证方式：新增/更新 `tests/test_document_import.py` 并通过。
- [x] 6.2 验证降级路径：清空 `MYKB_PARSER_URL` 时 Markdown 导入成功、docx 条目失败并给出未启用提示。验证方式：集成测试覆盖两种上传结果。
- [x] 6.3 运行 `make check` 与 `make build`，确认后端 lint/typecheck/test 与前端构建全部通过。验证方式：命令退出码为 0。
- [x] 6.4 更新部署文档：sidecar 容器（无出网、资源限额、模型预置）与后端 `git-lfs` 安装要求。验证方式：按文档从零启动一次环境并完成 docx 导入。

## Workflow follow-up

- 评审通过后归档该变更，并确认主 specs 已合入 `document-conversion`、`document-import`、`knowledge-import`、`knowledge-storage`。
