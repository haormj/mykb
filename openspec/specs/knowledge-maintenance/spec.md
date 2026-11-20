# knowledge-maintenance Specification

## Purpose

检测知识过期与源数据变更，沿血缘定位受影响知识，支持重审、废弃与回滚。

## Requirements

### Requirement: 过期与变更检测
系统 SHALL 检测源数据的过期与变更，依据 stale_after 字段或对 resource 指向的外部源做新鲜度检查。

#### Scenario: 源数据过期
- **WHEN** 某源数据概念的 stale_after 时间已过或外部源发生变更
- **THEN** 系统识别该概念为过期或待重审

### Requirement: 血缘回溯定位
系统 SHALL 沿 sources 链回溯，找出受源数据变更影响的所有业务知识。

#### Scenario: 定位受影响知识
- **WHEN** 一条源数据被标记为变更或过期
- **THEN** 系统返回所有通过 sources 字段依赖该源数据的业务知识

### Requirement: 标记重审
系统 SHALL 将受源数据变更影响的业务知识标记为待重审（needs-review）。

#### Scenario: 业务知识待重审
- **WHEN** 业务知识依赖的源数据发生变更
- **THEN** 该业务知识 status 更新为 needs-review，进入重新提取与审核流程

### Requirement: 废弃与取代
系统 SHALL 支持将过时知识标记为 deprecated，并通过 superseded_by 字段指向其替代概念。

#### Scenario: 知识被取代
- **WHEN** 某业务知识被新的业务知识取代
- **THEN** 旧知识 status 置为 deprecated，其 superseded_by 字段指向替代概念

### Requirement: 索引回滚
系统 SHALL 支持将检索引擎回滚到此前记录的 git commit 版本对应的索引。

#### Scenario: 回滚索引
- **WHEN** 检索引擎索引因错误变更被污染
- **THEN** 系统可回滚到此前记录的 commit 版本对应的索引状态
