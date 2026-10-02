# state.db 合并详解（旧库 → 当前库）

2026-08 实战（旧库 schema v23 → 当前库 v25，129 会话 / 15,871 消息合并成功）。

## 前置

- 备份：`shutil.copy2(CUR_DB, CUR_DB + '.bak.<ts>')`，失败可回滚。
- 连接：当前库 `sqlite3.connect(CUR_DB, timeout=60)` + `PRAGMA busy_timeout=60000`（网关持有 WAL 写锁）；旧库以只读打开：`sqlite3.connect('file:OLD?mode=ro', uri=True)`。
- 单事务：`BEGIN IMMEDIATE` → 全部插入 → `commit()`；任何异常 `rollback()` 后 raise（保证幂等重跑）。

## Schema 差异处理

```python
cur_cols = [d[1] for d in cur.execute('pragma table_info(sessions)')]
old_cols = [d[1] for d in old.execute('pragma table_info(sessions)')]
# 断言：旧库列集 ⊆ 当前库列集 (old_cols <= cur_cols)；仅当旧库有当前库缺失列时才停下人工决策
# 插入只写「新旧共有的列」(用旧库列名)，当前库多出的列不写 -> 自动走其 DEFAULT
```

实测：v23→v25 时 sessions 多了 `last_activity_at/last_activity_description/last_activity_provenance/title_source` 等列；messages 列集合两版一致。

⚠️ **切勿 `vals = [d.get(c) for c in cur_cols]` 直接补 None**：当前库的新增列里有些是
`NOT NULL DEFAULT x`（实测 v25→v30：messages 多 `_compressed_summary INTEGER NOT NULL DEFAULT 0`、
`display_identity BLOB`、`display_order INTEGER`；sessions 多 `git_metadata_generation/hidden/
transport_profile/tool_names/compression_recovery_deadline`，其中 `git_metadata_generation` 与
`hidden` 是 `NOT NULL DEFAULT 0`）。补 None 会直接撞 NOT NULL 报错。正确做法：
`ins_cols = [c for c in old_cols if c != 'id']`，INSERT 只列这些列，其余列交 DEFAULT
（`active`/`compacted`/`_compressed_summary` 等即自动取默认，消息才会可见）。

v25→v30 另两点实战补充：
- **FTS 全自动**：新旧库的 `messages_fts`/`messages_fts_trigram` 都由 `messages` 上的 AFTER INSERT
  触发器维护（触发器 WHEN 依赖 `state_meta.fts_rebuild_high_water`，缺该键时 `new.id > -1` 恒真、
  正常触发）。所以插消息即自动建索引，无需手工 rebuild；插完核对
  `count(messages_fts) == count(messages)` 即可。
- **当前库 FTS 的 content 是视图** `messages_fts_src`（不是表 `messages`）——不要对它做 rebuild。
- 旧库标题全部非空时（本次 142/142）逐个去重，冲突用完整 sid 后缀，逐行 try/except。

## 消息 id 重映射

```python
cur_max = cur.execute('select coalesce(max(id),0) from messages').fetchone()[0]
mid = cur_max
for row in old.execute('select * from messages'):
    d = dict(zip(omcols, row))
    if d['session_id'] not in kept: continue   # kept = 当前id ∪ 本次导入的id
    mid += 1; d['id'] = mid
    cur.execute(f"INSERT INTO messages ({','.join(cmcols)}) VALUES ({','.join('?'*len(cmcols))})",
                [d.get(c) for c in cmcols])
```

只导入 `session_id` 属于最终 sessions 表的消息（跳过与当前 id 撞车的旧会话的消息）。

## sessions.title 部分唯一索引（本案例最大坑）

```sql
CREATE UNIQUE INDEX idx_sessions_title_unique ON sessions(title) WHERE title IS NOT NULL
```

- NULL 可重复 → 不设标题也能插入；但回填标题会撞车（旧库标题全 NULL，需从首条非空 user 消息回填）。
- 旧会话首条消息大量重复（同一任务的多次会话）→ 去重必须用**完整 sid 后缀 + 计数器**：

```python
used_titles = set(t for (t,) in cur.execute("select title from sessions where title is not null"))
for sid in imported_ids:
    m = cur.execute("select content from messages where session_id=? and role='user' and content!='' order by id limit 1", (sid,)).fetchone()
    t = re.sub(r'\s+', ' ', m[0]).strip()[:80] if m and m[0] else ''
    cand, i = t, 0
    while cand in used_titles:
        i += 1
        cand = f'{t} [{sid}]' if i == 1 else f'{t} [{sid}][{i}]'
    try:
        cur.execute("update sessions set title=?, title_source='import' where id=?", (cand, sid))
        used_titles.add(cand)
    except sqlite3.IntegrityError as e:
        log(f'跳过 sid={sid}: {e}')   # 失败留 NULL, 绝不中断整体合并
```

**绝不用 `sid[:6]`**：时间戳型 id（`20260722_21533_xxx`）前 6 位全是 `202607`，同组重复标题的后缀必撞车 → IntegrityError。逐行 try/except 兜底，保证单条失败不炸整个事务。

## FTS 索引维护（三种形态，先查 DDL 再决定）

```python
fts_sql = cur.execute("select sql from sqlite_master where name='messages_fts'").fetchone()
fts_external = 'content=' in (fts_sql[0] if fts_sql else '')
has_triggers = cur.execute("select count(*) from sqlite_master where type='trigger' and tbl_name='messages'").fetchone()[0] > 0
```

| 形态 | 处理 |
|---|---|
| external-content（DDL 含 `content=`） | `INSERT INTO messages_fts(messages_fts) VALUES('rebuild')` 安全，重建全量 |
| standalone + 有触发器 | 触发器在 INSERT 时自动写 FTS，无需处理（验证行数即可） |
| standalone + 无触发器 | 手动插行：`INSERT INTO messages_fts(rowid, content, tool_name, tool_calls) VALUES (?,?,?,?)`（列按当前 schema） |

⚠️ standalone 表上执行 `rebuild` 会清空索引重建为空（无 content 表可读）。

## 标题回填与验证

- 回填后会话列表可读：`select id, title, datetime(started_at,'unixepoch','localtime') from sessions order by started_at desc`
- 验证：`PRAGMA quick_check` = ok；`select count(*) from messages_fts` == `select count(*) from messages`
- 检索测试：`select count(*) from messages_fts where messages_fts match '关键词'`（中文直接 match 可用）
- 提交后再用 `session_search` 工具实测（工具读的就是这个库）。
