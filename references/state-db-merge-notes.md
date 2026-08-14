# state.db 跨版本合并笔记 (observed Aug 2026, Hermes schema v23 → v25)

## 观察到的 schema 漂移

| 对象 | v23 (旧) | v25 (当前) | 合并影响 |
|---|---|---|---|
| schema_version | 23 | 25 | 无直接作用，仅提示差异存在 |
| sessions 列 | 基础集 | 新增 `last_activity_at`, `last_activity_description`, `last_activity_provenance`, `title_source` 等 | 旧行按当前列清单 INSERT，缺失列填 NULL |
| messages 列 | 与 v25 相同 (24 列) | 同左 | 集合必须一致（脚本 assert）；列顺序无关，用显式列清单 |
| messages_fts 列 | `[content]` 单列 | `[content, tool_name, tool_calls]` 三列 | 按 DDL 判断 external-content 再重建/手动补 |
| sessions.title | 无唯一约束 | **部分唯一索引** `CREATE UNIQUE INDEX idx_sessions_title_unique ON sessions(title) WHERE title IS NOT NULL` | NULL 可重复；非 NULL 必须唯一 → 标题回填必须去重 |
| sessions.id | TEXT | TEXT | 无唯一约束风险（旧库曾出现同 id 多行，仍可插入） |

## 关键坑

1. **标题回填撞唯一索引**：多个会话首条消息相同（slash 命令重复调用常见）。
   用 `sid[:6]` 做去重后缀会失败——时间戳式会话 id `YYYYMMDD_HHMMSS_xxxxxx`
   同一天的会话前 6 位全是 `202607` 之类 → 后缀相同 → 第二次 UPDATE 直接
   `UNIQUE constraint failed: sessions.title`，整个事务回滚。
   **正确做法**：后缀用完整 sid + 计数器兜底 + 每条 UPDATE 单独 try/except（失败留 NULL）。

2. **消息 id 冲突**：两个库的 messages.id 都是从 1 开始的 INTEGER。合并时重映射为
   `cur_max + i`（i 为导入序号）。显式插入更高 id 时 sqlite_sequence 自动更新，无需手工处理。

3. **FTS 三种形态**（查 `sqlite_master` 里 messages_fts 的 DDL）：
   - `content=` 出现在 DDL → external-content 表 → `INSERT INTO messages_fts(messages_fts) VALUES('rebuild')`
   - 无 `content=` 且无触发器 → standalone，须手动按**重映射后的 id** 逐行 INSERT
   - 有触发器（v25 实测 `触发器=True`）→ INSERT messages 时自动维护，无需处理
   注意：对 standalone 表执行 rebuild 会清空已有索引（它只从 content 表重建），不要乱用。

## 活网关环境

- state.db 是 WAL 模式：同一时刻一个写者。`BEGIN IMMEDIATE` + `PRAGMA busy_timeout=60000`，
  事务保持短小（1.6 万行 ≈ 几秒），网关的写会排队等待而非失败。
- 合并失败必须 rollback，脚本幂等（会话按 id 去重、.env 只追加缺失键），可安全重跑。
- 合并完成后 `session_search` 立即可检索旧会话（标题回填后显示正常），**无需重启**。
- `.env`/`.profile` 凭据在网关启动时载入 → 新键对已运行进程不生效，重启后才可见。

## 会话 id 格式（去重/匹配时注意）

- 12 位十六进制：`0c106434e6e6`（webui 会话）
- 时间戳式：`20260722_21533_xxxxxx`（旧 CLI/网关会话）—— 前缀按天相同，截断比较必踩坑

## 旧库附带资产（可选恢复）

- `cron/executions.db`、`kanban.db`：常为空（无历史任务），可跳过
- `sessions/request_dump_*.json`：消息冗余副本，DB 已含全部内容，无需导入
- `models_dev_cache.json` / `provider_models_cache.json`：缓存，会自动重建
- 旧 `skills/` 目录可能在快照中整体缺失（自定义技能丢失），但 `~/.agents/skills/` 常幸存
