## Phase 5 — 技能 git 仓库恢复

- 快照缺 `skills/` 时：从 GitHub 恢复（git 协议被掐时用 API tarball 法）——
  见 `references/github-skill-recovery.md`。
- 下载/解压的技能目录没有 `.git`，按源仓库重连并重做提交（脚本 `scripts/reconnect_skill_repos.py`）：
  1. `git init -b main`；`git remote add origin <repo-url>`（源仓库未知用 GitHub API 探测；
     注意**私有仓库不在公开列表**，但带 PAT 的 tarball 能下载成功，别凭公开列表判断不存在）。
  2. 仓库级身份：user.name/email/signingkey/commit.gpgsign。
  3. **先测 GPG 非交互签名**：`echo test | timeout 20 gpg --batch --yes --sign
     --local-user <KEYID> --output /dev/null`——成功才 `git commit -S`，失败降级
     `git -c commit.gpgsign=false commit`。
  4. `git add -A && git commit -S`；验证 `git log --format=%G? -1` == `G`。
  5. 已复制到多处（如技能树）的目录：先 `diff -rq --exclude=.git A B` 确认一致，再
     `cp -a A/.git B/.git` 同步；**不要 rm 用户放置的目录**。
- **重置提交 + 强制推送**（用户要求时）：先 `git fetch origin <branch>` + `git diff --stat
  origin/<branch> HEAD`——树完全一致说明纯历史重写、零内容风险；`git push -u --force origin
  <branch>`（推送前用 API 确认远程默认分支）；推送后 `ls-remote` 比对远程 HEAD == 本地 HEAD。
  **只处理用户自己账号下的仓库**，第三方技能仓库（非用户账号）一律不碰。
- SSH 可用优先 SSH origin；未注册时用 HTTPS+PAT（脚本内读 token，不打印）。
