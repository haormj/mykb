# Spec Delta

## MODIFIED Requirements

### Requirement: 角色能力约束
系统 SHALL 按能力矩阵约束四档角色可执行的操作：viewer 只读，editor 可导入、起草并在该库上运行评测，admin 可审核合并、维护、管理成员与设置，owner 可删除、转移与修改远程。

#### Scenario: viewer 只读
- **WHEN** viewer 尝试导入、起草或审核
- **THEN** 系统拒绝该操作

#### Scenario: editor 贡献内容
- **WHEN** editor 导入文档、起草知识或对目标库运行评测
- **THEN** 系统允许该操作

#### Scenario: 运行评测要求目标库角色
- **WHEN** 用户对某知识库运行评测但不具备该库 editor 及以上角色
- **THEN** 系统拒绝该次运行

#### Scenario: admin 管理与审核
- **WHEN** admin 审核合并草稿、修改设置或管理成员
- **THEN** 系统允许该操作

#### Scenario: owner 高危操作
- **WHEN** owner 删除、转移知识库或修改 git 远程地址
- **THEN** 系统允许该操作，其他角色被拒绝

## ADDED Requirements

### Requirement: 评测资源授权
系统 SHALL 以评测集创建者所有权管理评测集（创建者可改删、他人只读可用），并以目标知识库成员身份约束评测运行及其结果的可见性：结果仅对目标库 viewer 及以上成员与平台管理员可见。

#### Scenario: 所有者管理题集
- **WHEN** 评测集创建者修改或删除该评测集
- **THEN** 系统允许该操作

#### Scenario: 非所有者只读复用
- **WHEN** 非创建者查看并使用某评测集
- **THEN** 系统允许查看与运行但拒绝修改

#### Scenario: 结果按目标库可见
- **WHEN** 用户查看某次评测运行结果
- **THEN** 仅当该用户是目标库成员或平台管理员时才可见该结果

#### Scenario: 非成员不可见结果
- **WHEN** 非目标库成员且非平台管理员的用户请求某次运行结果
- **THEN** 系统拒绝并返回无权访问
