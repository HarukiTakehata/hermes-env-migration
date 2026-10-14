# 网络受限时从 GitHub 恢复技能（API tarball 法）

2026-08 实战：容器内 git 协议直连 github.com 被掐（`GnuTLS recv error`、`Error in the HTTP2 framing layer`、`Could not connect to server` 连接超时），但 **api.github.com 走 curl 完全正常**。旧机器的自定义技能（8 个仓库，含 2 个私有）全部用此法恢复。

## 1. 先确认技能在 GitHub 上

用户快照里 `.hermes/skills/` 缺失时，先怀疑技能被推到 GitHub（本案例：用户 2026-08-12 推送了 8 个技能仓库，仓库名=技能名）。

```bash
TOK=$(grep -E '^GITHUB_(CLASSIC|FINE_GRANTED)_PAT=' "${HERMES_HOME:-/home/user/.hermes}/.env" | head -1 | cut -d= -f2- | tr -d '"')
# 令牌归属账号
curl -s -H "Authorization: Bearer $TOK" https://api.github.com/user
# 账号仓库列表（按更新时间，一眼看出最近推送的技能）
curl -s -H "Authorization: Bearer $TOK" "https://api.github.com/user/repos?per_page=100&sort=updated"
# 按技能名搜（带 Bearer 的搜索包含令牌可访问的私有仓库）
curl -s -H "Authorization: Bearer $TOK" "https://api.github.com/search/repositories?q=<技能名>&per_page=10"
```

注意：`/users/<login>/repos` 只列公开仓库；**私有技能仓库要用带令牌的 `/user/repos` 或认证搜索才能看到**（本案例 university-environment-query、chinese-web-scraping 就是私有仓库）。

## 2. 优先试 SSH，再退回 API tarball

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -T git@github.com 2>&1 | grep -q "Hi " && echo SSH_OK
```

成功 → `git clone git@github.com:<owner>/<repo>.git`；失败（密钥未注册/SSH 被封）→ 走 API tarball。

## 3. API tarball 下载（核心方法）

```bash
BR=$(curl -s -H "Authorization: Bearer $TOK" "https://api.github.com/repos/<owner>/<repo>" | python3 -c "import json,sys; print(json.load(sys.stdin).get('default_branch') or 'main')")
curl -sL -H "Authorization: Bearer $TOK" "https://api.github.com/repos/<owner>/<repo>/tarball/$BR" -o repo.tar.gz
mkdir -p repo && tar xzf repo.tar.gz -C repo --strip-components=1
```

- 校验：`stat -c%s` 小于 ~1KB 就是失败（可能是错误 JSON），打印前 200 字节排查。
- 令牌只放 header（`Authorization: Bearer`），**不要嵌进 URL/argv**。
- 公开仓库可无令牌下载，但带令牌更稳（避免速率限制）。

## 4. 安装为 Hermes 技能

- 读每个仓库根目录 `SKILL.md` 的 frontmatter（name/description/metadata.tags）判断归属分类。
- 按旧布局放两层级：`$HERMES_HOME/skills/<category>/<name>/`（本案例：research/、creative/、minecraft/）。
- 装完验证：`skills_list`（数量增加）+ `skill_view` 抽查加载 + `find $HERMES_HOME/skills -name SKILL.md | wc -l`。
- 分类参考旧目录结构（bash_history 里 `cd .hermes/skills/<category>/<name>/` 的痕迹最可靠）；无痕迹时按 tags 推断。

## 5. 其他

- 相关技能名引用（related_skills）里提到的技能可能根本没上传（本案例 `tesseract-ocr-chinese-image`、`video-content-summarizer` 在 GitHub 上不存在）——先搜再下结论，找不到就用已有技能的功能覆盖（内置 pdf 技能的 OCR 提取、multi-video-summarizer）。
- 用户旧记忆里还有另一条路：`gh-proxy.org` / `github.chenc.dev` 镜像前缀（`git clone https://gh-proxy.org/https://github.com/...`），git 协议能通时可用。
- 凭据键名参考：旧 `.env`/`.profile` 中 GitHub 用 `GITHUB_CLASSIC_PAT`（ghp_）与 `GITHUB_FINE_GRANTED_PAT`（github_pat_），旧 `GITHUB_TOKEN` 已弃用。
