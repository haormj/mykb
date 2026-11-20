# Spec Delta

## MODIFIED Requirements

### Requirement: 版本化同步
系统 SHALL 为每个知识库独立维护检索引擎中的索引，并将其与该库 knowledge 层级的 git commit 绑定，支持定时或手动触发同步。

#### Scenario: 定时同步
- **WHEN** 某知识库的同步任务被调度或手动触发
- **THEN** 系统将该库当前 knowledge 层级的已审核概念同步到检索引擎，并记录对应的 git commit 版本

## ADDED Requirements

### Requirement: 按知识库隔离检索
系统 SHALL 在检索与问答请求中限定目标知识库，只返回该库已审核的业务知识，不跨库混检。

#### Scenario: 指定库检索
- **WHEN** 请求指定某个知识库发起检索
- **THEN** 系统只在该库的索引中检索并返回结果

#### Scenario: 不返回他库内容
- **WHEN** 请求指定知识库 A 发起检索
- **THEN** 结果不包含知识库 B 的内容
