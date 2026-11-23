# document-conversion Specification

## Purpose

把用户上传的本地办公文档在系统内部（不调用外部接口）转换为 markdown，并产出可追溯的 OKF 源数据输入。

## Requirements

### Requirement: 仅使用内部转换服务

系统 SHALL 仅通过部署在内部网络的转换服务完成格式转换，不得调用外部接口或将文档内容发送到内网之外；转换所需的模型与运行环境必须预先就绪。

#### Scenario: 内网内完成转换
- **WHEN** 用户导入需要转换的文档
- **THEN** 系统只调用内部转换服务，不发起任何外部网络请求

#### Scenario: 未配置转换服务
- **WHEN** 系统未配置内部转换服务且用户上传需要转换的格式
- **THEN** 该条目失败并提示转换服务未启用，且不写入任何概念

#### Scenario: 转换服务不可达
- **WHEN** 转换服务不可达或返回无法恢复的错误
- **THEN** 任务置为 failed 且可重试，不写入半成品概念

### Requirement: 支持格式范围

系统 SHALL 在 v1 支持将 `.docx` 转换为 markdown，并对 `.md`、`.markdown` 直通；`.pdf`、旧版 `.doc` 等暂不支持的格式 SHALL 被明确拒绝并提示转换范围。

#### Scenario: docx 转换
- **WHEN** 用户导入 `.docx` 文件
- **THEN** 系统通过内部转换服务产出 markdown 正文

#### Scenario: markdown 直通
- **WHEN** 用户导入 `.md` 或 `.markdown` 文件
- **THEN** 系统保留其原有 frontmatter 与正文，不做格式转换

#### Scenario: 暂不支持的格式
- **WHEN** 用户导入 `.pdf`、`.doc` 或其他未支持格式
- **THEN** 系统拒绝该文件并提示当前支持的类型

### Requirement: 转换产物契约

系统 SHALL 使转换产出 markdown 正文、文档标题与图片资产，并把 markdown 正文作为源数据概念 body，把图片资产作为派生资产随该概念存放。

#### Scenario: 产出标题
- **WHEN** 转换成功
- **THEN** 概念标题取文档内标题信息，缺失时回退为原始文件名

#### Scenario: 产出图片资产
- **WHEN** 文档包含图片且转换成功
- **THEN** 图片作为派生资产随概念写入同一知识库，markdown 使用指向资产的相对路径

### Requirement: 转换来源标记

系统 SHALL 在转换产出的概念 frontmatter 中记录来源格式、原始文件名、原始内容指纹、原始大小与转换实现标识，并使 resource 仅作为逻辑来源标识。

#### Scenario: 记录来源信息
- **WHEN** 一次文档转换成功
- **THEN** 概念 frontmatter 包含来源格式、原始文件名、原始内容指纹、原始大小与转换实现标识

#### Scenario: 原件删除后仍可识别
- **WHEN** 原始文档已按约定删除
- **THEN** 概念仍可通过内容指纹与来源信息被识别和追溯，resource 不被承诺可回取

### Requirement: 转换产物限额

系统 SHALL 对单文档转换产物的图片数量、资产总大小与 markdown 大小施加配置上限；超出上限的条目标记为失败，且不写入部分产物。

#### Scenario: 图片资产超限
- **WHEN** 单文档产出的图片数量或资产总大小超过配置上限
- **THEN** 该条目失败并记录原因，不写入该文档的 markdown 或资产

#### Scenario: markdown 超限
- **WHEN** 转换产出的 markdown 超过配置大小上限
- **THEN** 该条目失败并记录原因

### Requirement: 转换失败按条目隔离

系统 SHALL 对每个上传条目独立执行转换；单条转换失败只影响该条目并计入任务失败计数，其余条目继续处理。

#### Scenario: 单条失败其余继续
- **WHEN** 一个导入任务包含多个条目且其中一个转换失败
- **THEN** 其余条目正常写入，任务状态为 partial 并记录失败条目

#### Scenario: 失败不落半成品
- **WHEN** 某条目转换失败
- **THEN** 该条目对应的概念与资产均不写入知识库
