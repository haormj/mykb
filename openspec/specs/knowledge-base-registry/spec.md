# knowledge-base-registry Specification

## Purpose

管理知识库的创建与查询，并为每个知识库维护独立的本地 git 仓库（远程可选），作为该库知识内容的存储单元。

## Requirements

### Requirement: 创建知识库
系统 SHALL 支持已登录用户创建知识库，至少提供名称，创建者自动成为该知识库的 owner。

#### Scenario: 创建成功
- **WHEN** 已登录用户提交未被占用的知识库名称
- **THEN** 系统创建知识库，并记录创建者为 owner

#### Scenario: 未登录拒绝
- **WHEN** 未认证请求尝试创建知识库
- **THEN** 系统返回未授权错误

### Requirement: 命名与路径唯一
系统 SHALL 保证知识库名称、slug 与本地仓库路径唯一，重复的创建请求被拒绝。

#### Scenario: 名称重复被拒绝
- **WHEN** 用户使用已存在的知识库名称创建
- **THEN** 系统返回命名冲突错误

#### Scenario: 本地路径冲突被拒绝
- **WHEN** 计算出的本地仓库路径已被占用
- **THEN** 系统拒绝创建且不覆盖已有目录

### Requirement: 独立 git 仓库
系统 SHALL 为每个知识库在其专属目录初始化 git 仓库并建立 OKF 布局（raw、knowledge 与 bundle 根 index），不再包含评测层级。

#### Scenario: 新建时初始化
- **WHEN** 知识库创建完成
- **THEN** 其本地目录已存在且包含 raw、knowledge 与根 index 的布局及首个提交

#### Scenario: 不创建评测层级
- **WHEN** 初始化知识库的 OKF 布局
- **THEN** 目录中不存在 `evals` 层级

#### Scenario: 仓库不可写
- **WHEN** 本地仓库目录无法初始化或写入
- **THEN** 系统回滚该次创建并返回错误

### Requirement: 可选远程仓库
系统 SHALL 允许创建知识库时可选配置 git 远程地址；配置后校验可访问并推送，未配置时仅以本地 git 管理。

#### Scenario: 配置远程并推送
- **WHEN** 创建时提供可访问的远程地址
- **THEN** 系统完成初始化并将首个提交推送到该远程

#### Scenario: 未配置远程
- **WHEN** 创建时未提供远程地址
- **THEN** 知识库仅保留本地 git 仓库，创建成功

### Requirement: 补绑远程仓库
系统 SHALL 允许 owner 为已存在的本地知识库补绑远程仓库，且不得覆盖远程已有内容。

#### Scenario: 补绑空远程成功
- **WHEN** owner 为本地知识库绑定一个空的远程仓库
- **THEN** 系统设置远程并推送本地历史

#### Scenario: 非空远程被拒绝
- **WHEN** owner 尝试绑定一个已含提交的远程仓库
- **THEN** 系统拒绝绑定并提示需人工处理

### Requirement: 查询知识库
系统 SHALL 支持账号列出其可访问的知识库，并查看单个知识库详情。

#### Scenario: 列表仅含可访问项
- **WHEN** 账号请求知识库列表
- **THEN** 系统只返回该账号作为成员或平台管理员可见的知识库

#### Scenario: 查看详情
- **WHEN** 账号请求自己可访问的知识库详情
- **THEN** 系统返回名称、slug、git 配置与角色等元数据
