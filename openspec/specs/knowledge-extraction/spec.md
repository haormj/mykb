# knowledge-extraction Specification

## Purpose

将源数据加工融合为业务知识（AI 起草 + 人工审核），产出带血缘、可验证的业务知识概念。

## Requirements

### Requirement: AI 起草业务知识
系统 SHALL 使用 LLM 读取源数据概念并生成业务知识草稿，草稿标记 generated.by 为 ai、status 为 draft。

#### Scenario: 生成业务知识草稿
- **WHEN** 对一批源数据触发提取流程
- **THEN** 系统生成业务知识草稿概念，其 frontmatter 记录 generated.by 为 ai 且 status 为 draft

### Requirement: 人工审核
系统 SHALL 以 git 提交为单元提交草稿供人工审核，人工审核通过合并后为该概念打上 verified 标记并将 status 置为 stable。

#### Scenario: 审核通过
- **WHEN** 人工审核通过并合并业务知识草稿
- **THEN** 该概念 frontmatter 记录 verified 事件（verified.by 为 human），status 更新为 stable

#### Scenario: 审核不通过
- **WHEN** 人工审核拒绝业务知识草稿
- **THEN** 该草稿不被标记为 verified，不进入稳定状态

### Requirement: 记录加工血缘
系统 SHALL 使产出的业务知识概念通过 sources 字段引用其加工所依赖的源数据概念。

#### Scenario: 业务知识关联来源
- **WHEN** AI 起草或人工修订一条业务知识
- **THEN** 该概念的 sources 字段列出其依赖的源数据概念
