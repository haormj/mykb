# Spec Delta

## MODIFIED Requirements

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
