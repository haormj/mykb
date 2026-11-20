# Spec Delta

## Purpose

以 git 仓库承载 OKF bundle 作为知识唯一事实源，管理源数据与业务知识的分层结构、血缘、版本与生命周期元数据。

## ADDED Requirements

### Requirement: 知识分层存储
系统 SHALL 将知识以 OKF bundle 形式存储在 git 仓库中，并区分为源数据（raw）与业务知识（knowledge）两个层级，每个概念以带 YAML frontmatter 的 markdown 文件表示。

#### Scenario: 源数据落盘
- **WHEN** 数据导入流程产出源数据概念
- **THEN** 概念文件写入 bundle 的 raw 层级目录，且 frontmatter 包含非空 type 字段

#### Scenario: 业务知识落盘
- **WHEN** 数据提取流程产出业务知识概念
- **THEN** 概念文件写入 bundle 的 knowledge 层级目录

### Requirement: 血缘追溯
系统 SHALL 通过业务知识概念的 sources 字段记录其依赖的源数据概念，使任意业务知识可追溯至其来源。

#### Scenario: 追溯业务知识来源
- **WHEN** 用户查询某条业务知识的来源
- **THEN** 系统返回该概念 sources 字段引用的全部源数据概念

### Requirement: 知识版本化
系统 SHALL 以 git 提交作为知识的版本单位，并在 bundle 根 index.md 中声明 okf_version 与 bundle 版本。

#### Scenario: 变更形成新版本
- **WHEN** 任一概念发生变更并提交
- **THEN** 生成新的 git commit，可据此审计或回滚历史状态

### Requirement: 生命周期与信任元数据
系统 SHALL 使用 generated、verified、status、stale_after、superseded_by 字段表达知识的生产者、验证状态、生命周期与废弃关系。

#### Scenario: 知识被验证
- **WHEN** 人工审核通过某条业务知识
- **THEN** 该概念 frontmatter 记录 verified 事件，status 更新为 stable

### Requirement: OKF 合规性
系统 SHALL 保证 bundle 内所有概念文件符合 OKF 规范：每个非保留文件包含可解析的 YAML frontmatter 且含非空 type 字段，并保留未知扩展字段。

#### Scenario: 校验 bundle
- **WHEN** 对 bundle 执行合规校验
- **THEN** 缺少 type 的概念文件被报告为不合规
