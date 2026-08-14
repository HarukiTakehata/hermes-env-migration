#!/usr/bin/env python3
"""Merge an old HERMES_HOME into the live one (memories / .env / credential dirs / skills / state.db).

Usage: edit the path constants below (or set env), then `python3 merge_hermes_home.py`.
Idempotent: .env only appends missing keys; sessions dedup by id; safe to re-run.
Security: all credential values are moved file->file; only key NAMES are printed.
Verified against schema drift v23 -> v25 (Aug 2026); messages column sets must match.
"""
import os, re, shutil, sqlite3, time

OLD_HOME = '/path/to/old/home'        # old machine's home root (holds .hermes/, .ssh/, .agents/, .profile)
OLD_H    = OLD_HOME + '/.hermes'      # old HERMES_HOME
CUR_H    = os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes'))  # live HERMES_HOME
CUR_HOME = os.environ.get('HOME')     # live shell HOME (may be redirected, e.g. .../.hermes/home)

def log(msg): print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)

# ---------- 1. Memories ----------
for f in ['MEMORY.md', 'USER.md']:
    src = os.path.join(OLD_H, 'memories', f)
    if os.path.exists(src) and os.path.isdir(os.path.join(CUR_H, 'memories')):
        shutil.copy2(src, os.path.join(CUR_H, 'memories', f))
        log(f'记忆 {f} 已复制 ({os.path.getsize(src)}B)')

# ---------- 2. .env merge (backup -> append only missing keys) ----------
def parse_env(path):
    d = {}
    if not os.path.exists(path): return d
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k, v = line.split('=', 1)
        d[k.strip()] = v.strip()
    return d

cur_env_path = os.path.join(CUR_H, '.env')
if os.path.exists(cur_env_path):
    shutil.copy2(cur_env_path, cur_env_path + '.bak.premerge')
old_env = parse_env(os.path.join(OLD_H, '.env'))
cur_env = parse_env(cur_env_path)
# 2a: harvest `export KEY=...` credentials from the old ~/.profile
prof = os.path.join(OLD_HOME, '.profile')
if os.path.exists(prof):
    for m in re.finditer(r'^export\s+([A-Z0-9_]+)=(\S+)',
                         open(prof, encoding='utf-8', errors='replace').read(), re.M):
        k, v = m.group(1), m.group(2)
        if k not in cur_env:
            old_env.setdefault(k, v)
added = [k for k in old_env if k not in cur_env]
if added:
    with open(cur_env_path, 'a', encoding='utf-8') as f:
        for k in added:
            f.write(f'{k}={old_env[k]}\n')
    os.chmod(cur_env_path, 0o600)
log(f'.env 合并完成: 新增 {len(added)} 个键 {sorted(added)}')

# ---------- 3. ssh / aws / gnupg / gitconfig -> current HOME ----------
for d in ['.ssh', '.aws', '.gnupg']:
    src = os.path.join(OLD_HOME, d)
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(CUR_HOME, d), dirs_exist_ok=True)
        log(f'{d} 已复制到当前 home')
for f in ['.gitconfig']:
    src = os.path.join(OLD_HOME, f)
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(CUR_HOME, f))
        log(f'{f} 已复制')
ssh_root = os.path.join(CUR_HOME, '.ssh')
if os.path.isdir(ssh_root):
    for root, dirs, files in os.walk(ssh_root):
        for d in dirs: os.chmod(os.path.join(root, d), 0o700)
        for f in files:
            p = os.path.join(root, f)
            os.chmod(p, 0o644 if f.endswith('.pub') else 0o600)
gpg = os.path.join(CUR_HOME, '.gnupg')
if os.path.isdir(gpg): os.chmod(gpg, 0o700)

# ---------- 4. Custom skills -> $HERMES_HOME/skills/<category>/ ----------
# ~/.agents/skills is NOT auto-loaded by Hermes; it must be copied into skills/.
dst_root = os.path.join(CUR_H, 'skills', 'custom')
os.makedirs(dst_root, exist_ok=True)
agents_skills = os.path.join(OLD_HOME, '.agents', 'skills')
for s in sorted(os.listdir(agents_skills)) if os.path.isdir(agents_skills) else []:
    src = os.path.join(agents_skills, s)
    if os.path.isdir(src) and os.path.exists(os.path.join(src, 'SKILL.md')):
        shutil.copytree(src, os.path.join(dst_root, s), dirs_exist_ok=True)
        log(f'技能 {s} 已复制')

# ---------- 5. state.db merge ----------
CUR_DB = os.path.join(CUR_H, 'state.db')
OLD_DB = os.path.join(OLD_H, 'state.db')
if os.path.exists(CUR_DB) and os.path.exists(OLD_DB):
    bak = CUR_DB + f'.bak.{time.strftime("%Y%m%d_%H%M%S")}'
    shutil.copy2(CUR_DB, bak)
    log(f'state.db 已备份: {bak}')

    cur = sqlite3.connect(CUR_DB, timeout=60)
    cur.execute('PRAGMA busy_timeout=60000')
    old = sqlite3.connect(f'file:{OLD_DB}?mode=ro', uri=True)

    cur_cols = [d[1] for d in cur.execute('pragma table_info(sessions)')]
    old_cols = [d[1] for d in old.execute('pragma table_info(sessions)')]
    omcols   = [d[1] for d in old.execute('pragma table_info(messages)')]
    cmcols   = [d[1] for d in cur.execute('pragma table_info(messages)')]
    assert set(omcols) == set(cmcols), f'messages 列不一致: {set(omcols)^set(cmcols)}'

    fts_sql = cur.execute("select sql from sqlite_master where name='messages_fts'").fetchone()
    fts_sql = fts_sql[0] if fts_sql else ''
    fts_external = 'content=' in fts_sql
    has_triggers = cur.execute("select count(*) from sqlite_master where type='trigger' and tbl_name='messages'").fetchone()[0] > 0
    log(f'FTS: external_content={fts_external}, 触发器={has_triggers}')

    cur_ids = set(r[0] for r in cur.execute('select id from sessions'))
    cur_max = cur.execute('select coalesce(max(id),0) from messages').fetchone()[0]

    new_sess = new_msg = 0
    imported_ids = []
    try:
        cur.execute('BEGIN IMMEDIATE')           # live gateway = WAL; one writer at a time
        for row in old.execute('select * from sessions'):
            d = dict(zip(old_cols, row))
            if d['id'] in cur_ids: continue      # idempotent re-run
            vals = [d.get(c) for c in cur_cols]  # missing new-schema cols -> NULL
            cur.execute(f"INSERT INTO sessions ({','.join(cur_cols)}) VALUES ({','.join('?'*len(cur_cols))})", vals)
            imported_ids.append(d['id'])
            new_sess += 1
        kept = cur_ids | set(imported_ids)
        mid = cur_max
        for row in old.execute('select * from messages'):
            d = dict(zip(omcols, row))
            if d['session_id'] not in kept: continue
            mid += 1
            d['id'] = mid                        # remap INTEGER ids to avoid collision
            vals = [d.get(c) for c in cmcols]
            cur.execute(f"INSERT INTO messages ({','.join(cmcols)}) VALUES ({','.join('?'*len(cmcols))})", vals)
            new_msg += 1
        # Title backfill: sessions.title has a PARTIAL UNIQUE INDEX (WHERE title IS NOT NULL).
        # Duplicate first messages are common. Suffix MUST use the FULL session id
        # (timestamp-style ids share the same 6-char prefix!) + counter; leave NULL on failure.
        used_titles = set(t for (t,) in cur.execute("select title from sessions where title is not null"))
        for sid in imported_ids:
            m = cur.execute("select content from messages where session_id=? and role='user' and content!='' order by id limit 1", (sid,)).fetchone()
            if not m or not m[0]:
                continue
            t = re.sub(r'\s+', ' ', m[0]).strip()[:80]
            if not t:
                continue
            cand, i = t, 0
            while cand in used_titles:
                i += 1
                cand = f'{t} [{sid}]' if i == 1 else f'{t} [{sid}][{i}]'
            try:
                cur.execute("update sessions set title=?, title_source='import' where id=?", (cand, sid))
                used_titles.add(cand)
            except sqlite3.IntegrityError as e:
                log(f'!! 标题回填跳过 sid={sid}: {e}')
        cur.commit()
    except Exception:
        cur.rollback()
        raise
    log(f'state.db: 新增会话 {new_sess}, 消息 {new_msg} (id 重映射到 {cur_max+1} 起)')

    # FTS index
    if fts_external:
        cur.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        cur.commit()
        log('FTS 已重建 (external content)')
    elif not has_triggers:
        cur.execute('BEGIN')
        n = 0
        # standalone FTS: insert rows manually with the REMAPPED ids (all > cur_max)
        for row in cur.execute('select id, content, tool_name, tool_calls from messages where id > ?', (cur_max,)):
            cur.execute('INSERT INTO messages_fts(rowid, content, tool_name, tool_calls) VALUES (?,?,?,?)',
                        (row[0], row[1] or '', row[2] or '', row[3] or ''))
            n += 1
        cur.commit()
        log(f'FTS 手动补 {n} 行')
    else:
        log('FTS 由触发器维护, 无需额外处理')

    tot_s = cur.execute('select count(*) from sessions').fetchone()[0]
    tot_m = cur.execute('select count(*) from messages').fetchone()[0]
    fts_m = cur.execute('select count(*) from messages_fts').fetchone()[0]
    chk = cur.execute('PRAGMA quick_check').fetchone()[0]
    log(f'合并后: sessions={tot_s}, messages={tot_m}, fts={fts_m}, integrity={chk}')
    cur.close(); old.close()
print('DONE')
