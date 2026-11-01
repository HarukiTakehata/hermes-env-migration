## Phase 0 — 当前环境充分检查（先于一切，只读）

迁移开始前必须先摸清目标环境，方案才「针对性」：

- 主机/OS：`/etc/os-release`、`uname -a`、架构；**包管理器**（apt/dnf/apk/pacman/brew 等）。
- 用户与权限：`whoami` / `id`；`sudo -n true` 实测是否有 root；**容器检测**
  （`/.dockerenv`、`/proc/1/cgroup` 含 docker/containerd、rootfs 为 overlay）。
- 工具链现状（决定缺口清单）：python3/pip、node/npm、git、curl/wget、ffmpeg、jq、
  gcc/make/go、常用 CLI（free/uptime/ps 等 procps 类）。
- 网络连通性（pypi/github/目标 API 域），磁盘/内存余量。
