# knowledge-base-access-control Specification

## Purpose

通过知识库成员与四档角色控制库内操作权限，实现按知识库授权的资源级访问控制。

## Requirements

### Requirement: 成员与角色
系统 SHALL 维护知识库成员及其角色，角色分为 owner、admin、editor、viewer。

#### Scenario: 创建者成为 owner
- **WHEN** 用户创建知识库
- **THEN** 该用户成为该库唯一 owner 成员

#### Scenario: 添加成员
- **WHEN** 有成员管理权限的用户添加其他账号
- **THEN** 系统按指定角色建立该账号与知识库的成员关系

### Requirement: 库级授权校验
系统 SHALL 对知识库范围内的请求校验成员角色是否满足所需最低角色，非成员被拒绝；平台管理员不受库成员限制。

#### Scenario: 满足最低角色被放行
- **WHEN** 成员以不低于操作所需最低角色的身份发起请求
- **THEN** 系统放行该请求

#### Scenario: 非成员被拒绝
- **WHEN** 非该库成员的普通账号访问该库资源
- **THEN** 系统返回禁止访问错误

#### Scenario: 平台管理员放行
- **WHEN** 平台管理员访问任意知识库资源
- **THEN** 系统跳过库成员校验并放行

### Requirement: 角色能力约束
系统 SHALL 按能力矩阵约束四档角色可执行的操作：viewer 只读，editor 可导入、起草与评测，admin 可审核合并、维护、管理成员与设置，owner 可删除、转移与修改远程。

#### Scenario: viewer 只读
- **WHEN** viewer 尝试导入、起草或审核
- **THEN** 系统拒绝该操作

#### Scenario: editor 贡献内容
- **WHEN** editor 导入文档、起草知识或运行评测
- **THEN** 系统允许该操作

#### Scenario: admin 管理与审核
- **WHEN** admin 审核合并草稿、修改设置或管理成员
- **THEN** 系统允许该操作

#### Scenario: owner 高危操作
- **WHEN** owner 删除、转移知识库或修改 git 远程地址
- **THEN** 系统允许该操作，其他角色被拒绝

### Requirement: 成员管理边界
系统 SHALL 允许 admin 及以上添加或移除成员并调整角色，但不得授予高于自身的角色；owner 可在 owner 之间转让所有权。

#### Scenario: admin 管理普通成员
- **WHEN** admin 调整某成员的 editor 或 viewer 角色
- **THEN** 系统允许该调整

#### Scenario: 越权提升被拒绝
- **WHEN** admin 尝试把成员提升为 owner 或 admin 以上
- **THEN** 系统拒绝该调整

#### Scenario: owner 转让
- **WHEN** owner 将所有权转让给其他成员
- **THEN** 系统更新双方角色并使转让生效
