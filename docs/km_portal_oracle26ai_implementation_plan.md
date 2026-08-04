# KM Portal 新设计实施方案（Oracle 26ai）

## 1. 目标与边界

KM Portal 将从“把 Metadb 资产上传到 KBot”的同步脚本演进为独立的检索应用：Metadb 是只读业务上游；Oracle 26ai 是唯一的 AppDB；本地磁盘或 NAS 保存原始附件和 Markdown；KM Portal 提供资产检索与受引用约束的问答 API。

KBot 仍可作为现有下游兼容目标，但不再承担 Portal 的主索引或检索职责。迁移期可双写；验收后再决定是否停止 KBot 上传。

## 2. 现状、可复用实现与不复用范围

当前 `KmEngine` 已能轮询 Metadb，`KMFileMetaService` 能取得资产元数据，`SharePointClient` 能下载附件；但 `FileProcessor` 仅在内存中拼接 Markdown 并上传 KBot，没有持久化、索引或查询服务。

可从 `~/kbot3` 参考或抽取的实现模式：

- `core/database/oracle.py`：`python-oracledb`/SQLAlchemy 异步连接池、健康检查、事务与回滚边界。
- `microservices/file_processor/services/docling_service.py`：PDF、DOCX、PPTX、XLSX、HTML、Markdown 等格式的统一校验与 Docling 转换；CPU 密集转换由进程池执行。
- `services/search/kb_search.py` 与 `dao/repositories/txt_chunk_repo.py`：Oracle Text `CONTAINS`、`VECTOR_DISTANCE`、并行双路召回及 RRF 融合。
- 文件状态、重试和仓储分层可参考 `FileService`、`FileParseEngine`，但不直接使用其知识库表或 `kb_id` 模型。

不应直接复制 KBot 的全量 chunk 向量化方案。本项目首期仅对 **Asset Summary** 做向量与全文索引；附件全文保存在 Markdown 文件中，作为候选资产范围内的精搜和问答上下文来源。

## 3. 目标架构

```text
Metadb ──> 同步 Worker ──> 下载/转换/摘要/入库 ──> Oracle 26ai + Asset Store
                                                          ↑
调用方 ──> FastAPI Retrieval API ──> SQL 过滤 + Oracle 混合召回
                                      ──> 候选目录 rg 精搜 ──> 检索结果/问答
```

部署为两个独立进程：`worker` 处理长耗时 ETL；`api` 只读 Oracle 和 Asset Store，服务在线查询。二者共享配置、领域模型与存储根目录，但不共享内存队列。

## 4. Oracle 26ai 数据设计

所有表放在 Portal 自己的 schema，建议统一以 `KM_` 前缀命名。

| 表 | 核心职责 | 关键字段 |
|---|---|---|
| `KM_ASSET` | 一条 Metadb Asset 的当前可检索版本 | `asset_id`、标题、作者、分类、创建/更新时间、源链接、`storage_dir`、版本哈希、状态 |
| `KM_ASSET_ATTACHMENT` | 每个 SharePoint 附件及其转换产物 | `attachment_id`、`asset_id`、源 URL、文件名、MIME、大小、哈希、原件/Markdown 路径、转换状态 |
| `KM_ASSET_SUMMARY` | 每个 Asset 一条可检索摘要 | `asset_id`、摘要、关键词、模型/提示词版本、`VECTOR` 列、索引状态 |
| `KM_INGESTION_JOB` | 可恢复的任务状态和审计 | `job_id`、`asset_id`、来源版本、状态、尝试次数、锁定到期时间、错误码/摘要、下次重试时间 |
| `KM_QUERY_AUDIT`（可选） | 检索质量与性能观测 | 请求摘要、过滤条件、候选数、耗时、结果资产 ID；不得保存敏感正文 |

对 `KM_ASSET` 的作者、分类、日期、状态建立 B-tree 索引；对摘要文本建 Oracle Text `CONTEXT` 索引（中文 lexer 需由 DBA 配置）；对摘要向量建立 Oracle 26ai 推荐的 vector index，并由 DBA 根据数据量选择 HNSW/IVF 参数。JSON 只保存低频、可扩展的原始业务字段；高频过滤字段必须显式列化，不能依赖 JSON 扫描。

## 5. 检索设计

请求先解析为结构化过滤与关键词；无法可靠识别的过滤条件不应悄然生效，应回退为普通文本检索并在响应中标识。

1. Oracle SQL 硬过滤作者、类别、时间、状态和访问范围。
2. 对过滤后的 Summary 同时执行 Oracle Text 与向量召回；初期使用 KBot 已验证的 RRF 融合，返回 Top 20–50 个 `asset_id`。
3. 只对这些资产的 Markdown 文件执行 `rg` 精搜，按资产汇总命中附件、行号、上下文和精确短语得分。
4. “文档检索”直接返回资产卡片及附件命中；“知识问答”只把最终命中段落连同稳定的 `asset_id/attachment_id/行号` 引用送入 LLM，模型返回的每个结论必须绑定引用。

`rg` 必须通过参数数组调用，不拼接 shell；限定根目录为该 Asset Store、限制文件类型/大小/超时/结果数，并拒绝路径穿越。文件系统是精搜与上下文来源，Oracle 是权威元数据、任务和索引状态来源。

## 6. 实施阶段

### Phase 0：基础决策与验证

确认 Oracle 26ai schema、权限（含 Oracle Text）、向量维度和 embedding 模型；确认 NAS 挂载、备份、容量、访问权限；确定首期附件格式、最大文件大小、OCR 策略及 LLM 数据合规边界。用真实但脱敏的 50–100 个 Asset 验证 SharePoint 下载、Docling 转换、Oracle Text 中文分词和向量索引。

**完成标准：** 获得 DBA DDL/权限确认、存储 SLA 和一组端到端样本基线数据。

### Phase 1：应用骨架与 Oracle 持久化

引入 Oracle 异步连接池、仓储层、配置分组与 FastAPI 生命周期管理，参考 KBot 的连接池参数和健康检查。实现上述 Portal 专属表、迁移脚本、状态枚举和 `/healthz`。将当前内存级 `processing_ids` 替换为数据库任务领取：使用行锁或带租约的原子状态迁移，支持多 Worker、副本重启和任务超时回收。

**完成标准：** 可创建、查询和恢复任务；重复收到同一 `asset_id + last_update_time` 时不产生重复资产版本。

### Phase 2：可靠入库与文件落盘

把当前 `process_asset` 拆为“元数据规范化、任务领取、下载、持久化、转换、摘要、索引、完成回写”步骤。下载改为流式写入临时目录；校验类型、大小和 SHA-256 后原子发布到：

```text
<asset_store>/asset_<asset_id>/
  00_main.md
  original/01_<safe_name>.<ext>
  markdown/01_<safe_name>.md
```

`00_main.md` 固定包含资产 ID、标题、作者、分类、时间、源链接、业务简介和附件清单。转换层以 KBot 的 Docling Service 为起点；每种格式有明确成功、降级文本提取和失败状态。文件发布与 Oracle 更新采用补偿策略：数据库提交失败时保留可清理的临时目录；文件发布成功但索引失败时任务进入可重试的 `INDEX_PENDING`，不能回写 Metadb 为完成。

**完成标准：** 一个 Asset 的多附件、无附件、部分下载失败、转换失败及重跑均有确定结果和审计记录。

### Phase 3：摘要与 Oracle 混合索引

从 `00_main.md` 和已转换附件生成受长度限制的 Asset Summary、关键词和模型版本；将摘要及 embedding 写入 `KM_ASSET_SUMMARY`。实现 Oracle Text、向量检索和 RRF 融合，复用 KBot 的参数绑定与向量编码方式，不复制其 `KBOT_BIZ_TXT_EMBEDDING` 表。

先实现摘要级召回，不做全文 chunk embedding。必要时可在后续对“问答高频、长文档”增加按需 chunk 索引，作为独立优化而非首期依赖。

**完成标准：** 样本集上能正确执行作者/日期过滤、关键词检索、语义检索与融合排序，并可重建某个 Asset 的摘要索引。

### Phase 4：检索与问答 API

实现 `/search`、`/assets/{asset_id}`、`/answer` 和运行指标端点。搜索服务串联 SQL 过滤、Oracle 混合召回和候选目录 `rg`；回答服务实行上下文总量限制、超时、模型失败降级和逐条可验证引用。权限校验必须发生在 SQL 粗筛前，文件下载也必须基于 `attachment_id` 查询后映射，不暴露任意本地路径。

**完成标准：** 文档检索无需 LLM 即可返回可定位结果；问答响应不包含未被最终上下文采纳的引用；未授权资产不会出现在召回或错误信息中。

### Phase 5：影子运行、切换与运维

先对小批资产进行影子入库：继续现有 KBot 上传，同时写入 Portal 存储和 Oracle。比较资产数、附件数、转换成功率、摘要质量、检索 Top-K 命中率和端到端延迟；通过后开放只读 API，再按范围扩大同步。保留回滚开关，使 KBot 兼容上传可以独立启停。

为 Worker 和 API 建立指标：待处理/失败任务、租约超时、下载与转换耗时、索引延迟、Oracle 查询耗时、`rg` 耗时、召回数、零结果率和问答引用覆盖率。纯检索与问答分别定义 SLA；文档中“50ms”目标必须经热/冷缓存、NAS 和并发压测确认，不能作为未验证承诺。

## 7. 风险与实施原则

- 绝不在 Metadb 与 Portal 间做分布式事务；以 Portal 任务状态和幂等版本作为恢复依据，Metadb 成功标识最后回写。
- Oracle Text 的中文 lexer、VECTOR 索引类型、统计信息和执行计划需要 DBA 参与验收。
- NAS 上的 `rg` 延迟取决于挂载与页缓存；若压测不达标，优先缩小候选集和缓存 Markdown，再评估把精搜内容存入 Oracle Text，而非盲目扩大向量化范围。
- 禁止在日志、查询审计、错误详情或 LLM 提示词中泄露令牌、SharePoint 临时 URL 或无权限正文。

## 8. 建议的首个可交付版本

首版只覆盖：Metadb 增量同步、PDF/DOCX/PPTX/HTML 转 Markdown、资产级 Summary、Oracle Text + 向量 + RRF、候选目录精搜，以及文档检索 API。问答、OCR、Excel、高级权限同步、增量 chunk 索引和 KBot 下线均放在首版稳定后推进。
