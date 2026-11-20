# Spec Delta

## MODIFIED Requirements

### Requirement: 知识分层存储
系统 SHALL 以每个知识库对应一个独立 OKF bundle（位于该库自己的 git 仓库）的方式组织知识，并区分为源数据（raw）与业务知识（knowledge）两个层级，每个概念以带 YAML frontmatter 的 markdown 文件表示。

#### Scenario: 源数据落盘
- **WHEN** 数据导入流程产出源数据概念
- **THEN** 概念文件写入对应知识库 bundle 的 raw 层级目录，且 frontmatter 包含非空 type 字段

#### Scenario: 业务知识落盘
- **WHEN** 数据提取流程产出业务知识概念
- **THEN** 概念文件写入对应知识库 bundle 的 knowledge 层级目录

## ADDED Requirements

### Requirement: 知识库内容隔离
系统 SHALL 保证概念文件只写入所属知识库自己的 git 仓库，不同知识库之间的内容互不可见、互不影响。

#### Scenario: 写入互不串库
- **WHEN** 向某一知识库导入或提取知识
- **THEN** 概念只写入该库的 git 仓库，其他知识库的目录保持不变

#### Scenario: 查询不跨库
- **WHEN** 查询某个知识库的概念
- **THEN** 结果不包含其他知识库的内容
