
**Metadb 仅作为“业务上游（Data Source）”**，负责承载作者发布 asset 的原始业务过程；而**你的应用系统作为独立的“检索服务（Retrieval App）”**，通过定时 Job / 消息队列把 Metadb 的增量数据异步拉取过来，做解析、清洗、存盘和建立索引，再提供高并发的检索与问答能力。

这种读写分离（CQRS 架构）能够确保你的应用架构高度自主，完全不受业务源数据库的限制。

## 优化后的独立应用完整架构图

Plaintext

```
 ┌─────────────────────────────────────────────────────────┐
 │                   业务源头 (Source DB)                  │
 │   [ Metadb ] ──> 作者发布/更新 Asset (含有附件、作者等) │
 └────────────────────────────┬────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │ 异步 ETL / 同步 Job│
                    └─────────┬─────────┘
                              │
 ═════════════════════════════╪════════════════════════════════════════
 [ 你的应用系统 (Retrieval App System) ]
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 1. 入库与预处理管道 (Ingestion Pipeline)                              │
│  ├─ A. 抽取业务元数据 (Author, Email, Briefing, Category...)          │
│  ├─ B. 附件转换 (PDF / PPT / Word ──> Markdown)                      │
│  ├─ C. LLM 自动生成 Asset 高度概括的 Summary (300字)                 │
│  ├─ D. 本地/NAS 落盘: `/data/assets_store/<asset_id>/`                │
│  │     ├── 00_main.md (主信息)                                       │
│  │     └── 01_attachment.md (附件 Markdown)                          │
│  └─ E. 写入应用专属数据库 (App DB):                                    │
│        • 元数据 (用于 SQL 硬过滤)                                    │
│        • Summary Vector & BM25 索引 (用于语义/全文粗筛)               │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. 运行时检索与回答管道 (Runtime Processing Pipeline)                  │
│                                                                      │
│    [ 用户 Query: "张三写的关于 AIDP 架构的文档有哪些？" ]                 │
│                                │                                     │
│                                ▼                                     │
│     ┌──────────────────────────────────────────────────┐             │
│     │ 阶段一：App DB 结构化 + 混合粗筛 (Coarse Filter) │             │
│     │ • SQL 过滤 Author/Category                      │             │
│     │ • Summary 混合检索 (Vector + BM25)               │             │
│     │ ──> 耗时 <20ms，锁定位 Top 20-50 Asset 目录路径 │             │
│     └────────────────────────┬─────────────────────────┘             │
│                              │                                       │
│                              ▼                                       │
│     ┌──────────────────────────────────────────────────┐             │
│     │ 阶段二：Ripgrep 本地文件极速扫描 (Ripgrep Scan)  │             │
│     │ • 对 Top 50 目录下的 .md 文件跑短语正则          │             │
│     │ ──> 耗时 <5ms，秒杀伪相关，精准锁定命中 Asset    │             │
│     └────────────────────────┬─────────────────────────┘             │
│                              │                                       │
│                              ▼                                       │
│     ┌──────────────────────────────────────────────────┐             │
│     │ 阶段三：意图路由分流输出 (Response Routing)       │             │
│     │ ├─【文档检索】: 直接输出精确 Asset 卡片与附件列表│             │
│     │ └─【知识问答】: 提取命中 Asset 全文/Summary     │             │
│     │                + [Doc_X] 引标记送 LLM 生成回答 │             │
│     └──────────────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────────────┘
```

## 应用系统内部三大核心数据存储设计

在你的独立应用内部，数据将被优雅地拆分为三份，分别服务于不同的检索阶段：

### 1. App DB 结构化元数据表（SQL 过滤）

专门用来响应“谁写了多少篇”、“某时间段内的文档”等精确统计/过滤查询：

SQL

```
CREATE TABLE app_asset_metadata (
    asset_id VARCHAR PRIMARY KEY,
    author_name VARCHAR,
    author_email VARCHAR,
    solution_briefing TEXT,
    created_at TIMESTAMP,
    storage_dir VARCHAR,           -- 本地磁盘目录路径: /data/assets_store/asset_1001/
    attachment_names TEXT[]        -- 原附件文件名列表
);
```

### 2. App DB 向量 & 倒排索引表（混合粗筛）

**仅对 Asset 的 Summary 进行 Embedding 和 BM25 建索引**。因为 Summary 是由 LLM 精炼的 300 字摘要，体积极小，检索效率极高且完全不会把无关的底层细节混进来：

SQL

```
CREATE TABLE app_asset_summary_index (
    asset_id VARCHAR REFERENCES app_asset_metadata(asset_id),
    summary_text TEXT,             -- LLM 提取的核心摘要
    summary_vector VECTOR(1536)    -- Summary 的向量表示
);
```

### 3. 本地 / NAS 纯文本目录树（Ripgrep 精搜 & 上下文提取）

所有的长文本、附件 Markdown 统一保存在文件系统中，依靠 Linux 内存页缓存（PageCache）实现毫秒级磁盘/内存扫描：

Plaintext

```
/data/assets_store/
├── asset_1001/
│   ├── 00_main.md              <-- 方案简述 + Description + 属性
│   ├── 01_design_spec.md       <-- PDF 转换后的 MD
│   └── 02_slide_deck.md        <-- PPT 转换后的 MD
```

## 方案优势闭环总结

1. **对源头零侵入**：Metadb 只管业务写入，你的应用只管拉取消费，互不干扰，解耦非常彻底。
    
2. **解决“语义漂移”**：粗筛（Summary 向量/SQL）锁定范围 $\rightarrow$ Ripgrep 在 `.md` 上做词频/短语正则，强行过滤掉单纯提及 `Data Platform` 的无关文档。
    
3. **彻底消除“参考文档污染”**：
    
    - 纯文档搜索时： Ripgrep 命中了哪个 Asset 目录才列出哪个。
        
    - 知识问答时：结合 LLM 的 `[Doc_X]` 显式归因标签，没被采纳的 Chunk/文档直接丢弃，前端呈现的引用 100% 干净。
        
4. **极致性能**：跳过传统 RAG 繁重的全库 Chunk 向量计算，把主要工作交给**轻量 SQL + 毫秒级 Ripgrep**，大部分请求可在 **50ms 以内** 完成。