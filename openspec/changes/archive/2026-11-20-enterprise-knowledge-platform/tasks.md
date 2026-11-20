# Tasks

## 1. 项目骨架与 OKF 存储基础

- [x] 1.1 初始化 Python 项目结构（pyproject/依赖管理、目录布局、FastAPI 骨架），验证依赖安装成功且骨架服务可启动
- [x] 1.2 定义 OKF 概念数据模型（frontmatter 解析/序列化，覆盖 type/sources/generated/verified/status/stale_after/superseded_by），验证单元测试通过
- [x] 1.3 实现 OKF bundle 读写与合规校验（非保留文件须含 frontmatter 与非空 type），验证校验命令能正确报告缺失 type 的文件并放过未知扩展字段
- [x] 1.4 实现 raw/、knowledge/、evals/ 目录分层与 bundle 根 index.md 的 okf_version/version 声明，验证生成的 bundle 结构符合设计 D1

## 2. 数据导入

- [x] 2.1 定义 Connector 协议（sync + normalize 两阶段，Python Protocol），验证类型检查通过且文档说明两阶段职责
- [x] 2.2 实现连接器注册与发现机制，验证注册的连接器能被平台发现并列出
- [x] 2.3 实现首个连接器（Markdown/文件目录源）完成同步与归一化，验证产出的源数据概念落入 raw/ 且 resource 指向外部源、generated.by 为 process
- [x] 2.4 实现增量同步，验证对同一数据源重复执行同步不重复拉取已导入内容

## 3. 数据提取

- [x] 3.1 实现 AI 起草：LLM 读取 raw/ 源数据概念生成业务知识草稿（generated.by=ai、status=draft），验证草稿产出且字段正确
- [x] 3.2 实现草稿以 git PR 提交、人工 merge 后 CI 写入 verified（human）并将 status 置为 stable，验证 merge 后 frontmatter 符合预期
- [x] 3.3 实现 sources 血缘写入（草稿/修订时记录依赖的源数据概念），验证业务知识概念的 sources 正确指向其来源

## 4. 数据检索

- [x] 4.1 定义统一检索接口的能力清单与引擎适配抽象，验证接口契约文档完整且与具体引擎解耦
- [x] 4.2 实现「仅索引 verified 且 stable 业务知识」的过滤，验证源数据与草稿不进入检索引擎
- [x] 4.3 实现 markdown RAG 引擎适配器（对接 WeKnora），验证经统一接口可检索到已审核业务知识
- [x] 4.4 实现版本化同步（索引绑定 git commit，支持定时与手动触发），验证同步后记录的索引版本对应正确 commit
- [x] 4.5 实现 codegraph 代码检索适配器，验证代码感知检索返回符号/函数相关结果

## 5. 知识测评

- [x] 5.1 实现评测集管理（question/reference_answer/expected_concept/领域难度元数据），验证业务人员可创建并保存评测集
- [x] 5.2 实现评测任务运行与 A 分（expected_concept 命中 + 知识正确性，不经生成），验证 A 分计算结果正确
- [x] 5.3 实现 B 分（经统一接口端到端「问题→检索→生成→答案」并对比 reference_answer），验证 B 分计算结果正确
- [x] 5.4 实现分数展示与趋势（按评测集随时间记录分数），验证历史分数趋势可查看

## 6. 知识维测

- [x] 6.1 实现过期与变更检测（stale_after 过期 + resource 外部源新鲜度检查），验证过期/变更被正确识别
- [x] 6.2 实现 sources 血缘回溯，验证能定位所有依赖某条源数据的业务知识
- [x] 6.3 实现受影响业务知识标记 needs-review，验证状态正确更新并进入重提取流程
- [x] 6.4 实现废弃与取代（deprecated + superseded_by），验证旧知识指向替代概念
- [x] 6.5 实现索引回滚到历史 commit 对应版本，验证坏 merge 污染后能回滚

## 7. 前端（TypeScript，后续阶段）

- [x] 7.1 搭建 TypeScript 前端骨架（React/Next），验证开发服务可启动
- [x] 7.2 实现评测集管理界面，验证业务人员可创建并查看评测集
- [x] 7.3 实现审核界面（查看 AI 草稿 diff、确认合并），验证可通过界面完成审核流程
- [x] 7.4 实现分数看板，验证可查看各评测集的历史分数趋势

## 8. 集成验证

- [x] 8.1 跑通端到端流程：导入源数据 → AI 起草 → 人工 merge → 同步检索 → 运行评测集 → 查看分数 → 触发维测重审，验证全链路闭环
- [x] 8.2 运行 `openspec validate` 确认 change 通过校验

## Workflow follow-up

- Archive the change after review requirements are satisfied.
