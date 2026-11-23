# Spec Delta

## MODIFIED Requirements

### Requirement: 人工审核
系统 SHALL 以一个源文档变更的文档级评审 MR 为审核单元，MR 同时包含该文档的 raw 概念与受其影响的业务知识变更，供人工对照评审源与结果；人工合并后为通过的业务知识打 verified 并将 status 置为 stable。

#### Scenario: 审核通过
- **WHEN** 人工评审某份源文档的文档级 MR 并合并
- **THEN** MR 内的 raw 与业务知识一并进入主干，通过的业务知识 frontmatter 记录 verified 事件（verified.by 为 human），status 更新为 stable

#### Scenario: 审核不通过
- **WHEN** 人工拒绝某份源文档的文档级 MR 中的业务知识
- **THEN** 该业务知识不被标记为 verified、不进入稳定状态，raw 可按"部分接受"保留

#### Scenario: 对照源与结果评审
- **WHEN** 评审者打开一个文档级 MR
- **THEN** 可同时查看该文档的 raw 概念与其影响的业务知识变更，判断知识与源是否一致

### Requirement: 记录加工血缘
系统 SHALL 使产出的业务知识概念通过 sources 字段引用其依赖的源数据概念，并支持在 claim 级别记录每条断言的来源，以便源数据变更时定位受影响的断言而非整页重写。

#### Scenario: 业务知识关联来源
- **WHEN** AI 起草或人工修订一条业务知识
- **THEN** 该概念的 sources 字段列出其依赖的源数据概念

#### Scenario: claim 级来源
- **WHEN** AI 产出一条包含多条断言的业务知识
- **THEN** 每条断言记录其依赖的源数据概念 id，可独立追溯

## ADDED Requirements

### Requirement: 源数据变更自动触发提取
系统 SHALL 在源数据概念被新增、修改或删除时自动触发业务知识提取，无需人工逐次发起。

#### Scenario: 新增源数据
- **WHEN** 导入产生一条新的源数据概念
- **THEN** 系统自动为其触发提取并进入待审流程

#### Scenario: 修改源数据
- **WHEN** 已有源数据概念的内容指纹发生变化
- **THEN** 系统自动对依赖它的业务知识触发重新提取

#### Scenario: 删除源数据
- **WHEN** 一条源数据概念被删除
- **THEN** 系统自动对引用它的业务知识触发修订（见 knowledge-maintenance 的删除修订要求）

### Requirement: 提取串行执行
系统 SHALL 在同一知识库上串行执行提取，仅在一个文档级 MR 合并后，才基于最新主干为该库下一份变更文档生成新的 MR。

#### Scenario: 串行产生 MR
- **WHEN** 同一知识库有多份待处理文档
- **THEN** 系统一次只生成并等待一个文档级 MR，合并后再处理下一份

#### Scenario: 基于最新主干提取
- **WHEN** 生成某文档的 MR
- **THEN** 提取以当前已合并的最新主干为基准，避免与其他 MR 冲突

### Requirement: 提取约束与写盘前校验
系统 SHALL 以约束框架约束 LLM 产出：按业务知识类型套用模板与结构化 schema、以稳定规则派生概念 id、合并采用幂等增量方式，并在写入前校验 schema 合规、引用来源真实存在、无重复实体与断链；不通过校验的结果不得写入待审变更。

#### Scenario: 结构化产出
- **WHEN** 提取一条业务知识
- **THEN** 产出符合其类型模板与结构 schema，概念 id 由主题稳定派生（重跑落到同一路径）

#### Scenario: 校验失败
- **WHEN** 提取结果引用不存在的源数据或结构不合规
- **THEN** 系统不写入该变更并记录失败

#### Scenario: 幂等增量
- **WHEN** 对已存在的业务知识再次提取且语义无变化
- **THEN** 系统不产生内容变更

### Requirement: 提取任务在评审中流转
系统 SHALL 用持久化任务驱动提取，任务状态至少覆盖 converting、queued-for-review、reviewing、merged、rejected，并将结果写回任务记录。

#### Scenario: 任务等待评审
- **WHEN** 某文档提取完成并生成 MR
- **THEN** 对应任务状态为 queued-for-review 或 reviewing，直到 MR 合并或拒绝

### Requirement: 部分接受与回炉重做
系统 SHALL 允许在一个文档级 MR 内接受 raw 变更而将业务知识退回重新提取，而不丢弃已合格的 raw。

#### Scenario: raw 通过、知识退回
- **WHEN** 评审者认为 raw 转换合格但业务知识不合格
- **THEN** raw 保留，系统仅对该文档的业务知识重新提取并更新同一 MR

### Requirement: 周期页级体检
系统 SHALL 周期性地对业务知识做整页体检，检查 schema 合规、重复实体、断链与前后矛盾，弥补逐文档变更视角看不到整页累积问题。

#### Scenario: 整页体检发现问题
- **WHEN** 一条业务知识经多次文档变更累积后出现重复断言或断链
- **THEN** 系统报告问题并将其标记为 needs-review
