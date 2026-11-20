# Tasks

## 1. 数据模型与上传接口

- [x] 1.1 新增 `import_tasks` 模型与 Alembic 迁移，验证 `alembic upgrade head` 后表与索引存在、`downgrade` 可回滚
- [x] 1.2 实现 multipart 上传接口：类型/大小校验、创建 `queued` 任务、返回任务标识，验证允许类型成功、非法类型与超大文件被拒
- [x] 1.3 实现安全的临时目录创建与 zip 解包（拒绝路径穿越、限制条目数/总大小），验证恶意 zip 用例被拒

## 2. 执行器与状态机

- [x] 2.1 实现 per-KB 串行锁与进程内 worker，消费 `queued` 任务，验证同库并发任务排队、不同库并行
- [x] 2.2 实现状态迁移与计数回写（succeeded/partial/failed/cancelled）及错误摘要，验证各状态用例
- [x] 2.3 实现取消接口（editor 取消自己、admin 取消他人）与运行中取消的路径，验证权限与取消后停止写入
- [x] 2.4 实现启动时将残留 `running` 置为 `failed`，验证模拟崩溃后重启的恢复用例
- [x] 2.5 在任务终态清理上传临时目录，验证终态后目录不存在

## 3. 连接器与 git 写入

- [x] 3.1 新增 `upload` 来源适配并复用 markdown 归一化产出 OKF 概念，验证产出的 raw 概念含 type/frontmatter
- [x] 3.2 在 per-KB 锁内写入 `raw/`、提交 git、按配置 push，验证导入后 commit 递增且远程同步（若配置）
- [x] 3.3 单条目失败累加并继续以支持 `partial`，验证混入坏文件的用例得到 partial 与失败计数

## 4. 文档与任务查询接口

- [x] 4.1 实现任务列表与详情接口，验证只返回该知识库任务、鉴权正确
- [x] 4.2 实现文档列表接口（raw 概念 + 来源 + 所属任务），验证跨库不返回、字段完整

## 5. 前端文档页

- [x] 5.1 实现知识库「文档」页：文档列表、来源与任务状态展示，验证有数据/空态渲染
- [x] 5.2 实现「导入文档」弹窗：选择文件、提交、轮询任务状态、显示成功/部分失败/失败，验证完整导入流程
- [x] 5.3 按角色隐藏无权上传/取消操作，验证 viewer 看不到导入按钮

## 6. 集成验证与文档

- [x] 6.1 更新 README 说明上传限制、单 worker 约束与临时目录配置，验证按文档可完成一次上传导入
- [x] 6.2 集成测试：上传 → queued/running → succeeded/partial，文档出现在列表，验证 `pytest`、`mypy mykb`、`ruff check` 通过
- [x] 6.3 回归：跨库隔离、非法上传、取消任务、重启恢复，验证 `make check` 与 `npm run build` 通过

## Workflow follow-up

- 评审通过并完成 `scope-features-to-knowledge-base` 后归档该变更。
