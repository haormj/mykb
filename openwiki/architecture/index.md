# 文件

- [平台数据模型](data-model.md) - mykb 在 Postgres 中的元数据表及其关系：账号与角色、知识库与成员、导入任务与提取项、评测集/运行/结果、WeKnora 快照版本与概念映射、发布任务。
- [OKF 知识存储](knowledge-storage.md) - OKF bundle 的两级布局、概念模型与 frontmatter 字段、序列化往返、一致性校验，以及 git、分支与 Git LFS 如何承载知识库内容。
- [系统架构总览](overview.md) - mykb 的分层架构：Postgres 承载平台元数据、每个知识库独立 git/OKF 仓库承载内容、进程内任务执行器、可插拔检索后端与快照发布，以及从导入到评测的主流程。
