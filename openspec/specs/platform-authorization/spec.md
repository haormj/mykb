# platform-authorization Specification

## Purpose

定义平台级角色与权限，区分平台管理员与普通用户，并为平台管理操作提供授权校验。

## Requirements

### Requirement: 平台角色分配
系统 SHALL 为每个账号分配一个或多个平台角色，角色携带权限集合；新注册账号默认获得普通用户角色。

#### Scenario: 新账号默认角色
- **WHEN** 新账号注册成功
- **THEN** 该账号被授予普通用户角色

#### Scenario: 管理员角色
- **WHEN** 账号被授予平台管理员角色
- **THEN** 该账号具备平台级管理权限

### Requirement: 平台管理员校验
系统 SHALL 仅允许具备平台管理员角色的账号执行平台级管理操作。

#### Scenario: 管理员被放行
- **WHEN** 平台管理员访问平台管理接口
- **THEN** 系统允许该请求

#### Scenario: 普通用户被拒绝
- **WHEN** 普通用户访问平台管理接口
- **THEN** 系统返回禁止访问错误

### Requirement: 权限上下文
系统 SHALL 在鉴权时向请求上下文提供当前账号的角色与权限集合，供后续授权判断使用。

#### Scenario: 请求携带权限
- **WHEN** 受保护请求通过身份校验
- **THEN** 请求上下文包含该账号的角色与权限集合
