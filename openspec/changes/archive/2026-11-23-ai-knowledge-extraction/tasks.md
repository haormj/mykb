# Tasks

## 1. 提取约束框架（harness）

- [x] 1.1 定义业务知识类型模板与结构化 JSON 输出 schema，验证新增用例断言产出字段（title/summary/tags/claims/conflicts/open_questions）齐全
- [x] 1.2 实现稳定身份：概念 id 由主题/实体键派生，验证同一源重跑落到同一路径
- [x] 1.3 实现幂等增量合并（按 claim 比对，语义无变化不写盘），验证二次提取后 `git status` 干净
- [x] 1.4 实现写盘前校验（schema 合规 / 引用真实存在 / 无重复实体 / 无断链），验证违规结果不落盘并记录失败原因

## 2. claim 级血缘与提取元数据

- [x] 2.1 在业务知识中记录 `claims[].sources` 与 `x-extraction`（model/prompt_version/source_hash/task），验证断言可独立追溯
- [x] 2.2 补测试覆盖 claim 级追溯与 `x-extraction` 字段完整性

## 3. 待审队列与任务生命周期

- [x] 3.1 新增 Alembic 迁移（待审队列表 + `ImportTask` 新状态值 converting/queued-for-review/reviewing/merged/rejected），验证 `make migrate` 成功
- [x] 3.2 实现入队/出队与状态流转，验证状态机测试通过

## 4. 单飞提取 worker

- [x] 4.1 实现按 KB 单飞 worker（取队首 → 提取 → validate → 分支 → 等合并 → 下一篇），验证并发场景同库不会并发生成两个 MR
- [x] 4.2 实现重启恢复：残留未完成队列可续跑，验证回收测试通过

## 5. 导入与提取解耦

- [x] 5.1 改造导入收尾：转换后进入待审队列而非直接提交主干，验证导入后 `main` 无新增 raw、队列有记录
- [x] 5.2 导入任务终态改为 queued-for-review/reviewing，验证任务接口返回新状态

## 6. 文档级 MR

- [x] 6.1 生成 `change/doc-<slug>` 分支，内容 = 该文档 raw + `trace_affected` 的知识变更，验证分支内容与受影响页一致
- [x] 6.2 实现串行约束：MR N 合并后才基于最新主干生成 N+1，验证串行测试通过
- [x] 6.3 验证 raw 与知识同分支、merge 前主干不变

## 7. 文档级评审

- [x] 7.1 泛化 GitReview 为批量分支合并/拒绝并盖 `verified` + `stable`，验证通过/拒绝测试
- [x] 7.2 实现部分接受（接受 raw、业务知识退回重提取并更新同一 MR），验证测试
- [x] 7.3 review API 改为按文档级 MR 审批并可列出待审 MR，验证 API 测试

## 8. 变更检测与删除修订

- [x] 8.1 重新导入时比对内容指纹判定实质变更（避免仅时间戳误判），验证测试
- [x] 8.2 删除文档时按 claim 级血缘修订受影响知识并纳入该文档 MR，验证删除测试

## 9. 页级体检

- [x] 9.1 实现周期页级体检（schema / 重复实体 / 断链 / 冲突）并将问题页标记 needs-review，验证测试

## 10. 前端与文档

- [x] 10.1 文档页与评审页展示待审 MR、按文档聚焦、内联 claim 证据、部分接受操作，验证前端测试与 `make build` 通过
- [x] 10.2 更新 README 描述"导入 → 待审队列 → 提取 → 文档级 MR 评审 → 合并进索引"的新流程与新增配置，验证文档中的命令可照跑

## 11. 集成校验

- [x] 11.1 端到端：导入含 `.md` 与 `.docx` 的批次 → 逐文档 MR → 合并 → 检索命中，验证 `make check` 全绿
- [x] 11.2 验证检索仅索引 `verified && stable`、主干恒为已审内容

## Workflow follow-up

- 在项目评审要求满足后归档该 change。
- 归档后核对主 specs 已反映提取闭环的新行为。
