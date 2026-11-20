# knowledge-retrieval Specification

## Purpose

对外提供统一检索接口，屏蔽内部多引擎差异，将已审核业务知识版本化同步到检索引擎。

## Requirements

### Requirement: 统一对外接口
系统 SHALL 对外暴露稳定的知识检索接口，外部消费者不感知内部引擎（如 WeKnora、codegraph）的具体实现。

#### Scenario: 通过统一接口检索
- **WHEN** 外部消费者发起知识检索请求
- **THEN** 系统通过统一接口返回结果，调用方无需指定或感知底层引擎

### Requirement: 仅索引已审核业务知识
系统 SHALL 仅将 verified 且 stable 的业务知识同步到检索引擎，源数据不进入检索引擎。

#### Scenario: 过滤未审核知识
- **WHEN** 知识库中存在未审核的源数据与草稿
- **THEN** 这些内容不出现在检索引擎的索引中

### Requirement: 版本化同步
系统 SHALL 将检索引擎中的索引与 knowledge 层级的 git commit 绑定，并支持定时或手动触发同步。

#### Scenario: 定时同步
- **WHEN** 同步任务被调度或手动触发
- **THEN** 系统将当前 knowledge 层级的已审核概念同步到检索引擎，并记录对应的 git commit 版本

### Requirement: 多引擎适配
系统 SHALL 支持在统一接口之下挂接多个可替换的检索引擎，包括 markdown RAG 引擎与代码检索引擎。

#### Scenario: 替换检索引擎
- **WHEN** 将底层 markdown RAG 引擎替换为另一实现
- **THEN** 统一接口的外部行为保持不变，同一评测集可在不同引擎上重跑对比

### Requirement: 代码感知检索
系统 SHALL 支持通过代码检索能力（如 codegraph）对外提供代码感知检索。

#### Scenario: 代码检索请求
- **WHEN** 外部消费者发起代码感知检索请求
- **THEN** 系统通过代码检索引擎返回与代码符号、函数或实现相关的结果
