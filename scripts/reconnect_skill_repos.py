#!/usr/bin/env python3
"""把下载/解压得到的技能目录重连为 git 仓库并重做签名提交.

用法: python3 reconnect_skill_repos.py <基目录> <owner> [repo名1 repo名2 ...]
不传 repo 名则处理基目录下所有子目录。
每个 <基目录>/<repo名> 会: git init -b main -> remote origin
https://github.com/<owner>/<repo>.git -> 仓库级身份(优先全局 git config) -> GPG 非交互测试
-> git add -A + 签名提交 -> 验证 `git log --format=%G?` 为 G。
GPG 非交互不可用时自动降级为未签名提交 (repo 级 commit.gpgsign=false)。
凭据(如 PAT)只在脚本内部使用, 绝不打印。
"""
import os, subprocess, sys

def run(cmd, cwd, timeout=90):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, 'TIMEOUT'

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    base, owner = sys.argv[1], sys.argv[2]
    names = sys.argv[3:] or [d for d in sorted(os.listdir(base))
                             if os.path.isdir(os.path.join(base, d))]

    # 身份: 优先全局 git config, 再环境变量, 无则留空(不设置)
    name  = run(['git', 'config', '--global', 'user.name'], '/tmp')[1].strip() or os.environ.get('GIT_AUTHOR_NAME', '')
    email = run(['git', 'config', '--global', 'user.email'], '/tmp')[1].strip() or os.environ.get('GIT_AUTHOR_EMAIL', '')
    key   = run(['git', 'config', '--global', 'user.signingkey'], '/tmp')[1].strip() or ''

    # GPG 非交互签名测试: 成功才用 -S, 否则降级未签名
    sign_ok = False
    if key:
        rc, _ = run(['gpg', '--batch', '--yes', '--sign', '--local-user', key,
                     '--output', '/dev/null'], '/tmp', timeout=20)
        sign_ok = (rc == 0)
    print(f'身份: {name} <{email}> | GPG 签名: {"可用" if sign_ok else "不可用/未配置 -> 未签名提交"}')

    for n in names:
        d = os.path.join(base, n)
        if not os.path.isdir(d):
            print(f'!! {n}: 目录不存在, 跳过')
            continue
        if not os.path.isdir(os.path.join(d, '.git')):
            run(['git', 'init', '-b', 'main'], d)
        run(['git', 'remote', 'remove', 'origin'], d)
        rc, out = run(['git', 'remote', 'add', 'origin', f'https://github.com/{owner}/{n}.git'], d)
        if rc != 0:
            print(f'{n}: remote add FAIL {out[:120]}')
        for k, v in [('user.name', name), ('user.email', email),
                     ('commit.gpgsign', str(sign_ok).lower())]:
            if v:
                run(['git', 'config', k, v], d)
        if key:
            run(['git', 'config', 'user.signingkey', key], d)
        run(['git', 'add', '-A'], d)
        msg = f'chore: 重连技能仓库 {n} 并重做提交'
        if sign_ok:
            rc, out = run(['git', 'commit', '-S', '-m', msg], d)
        else:
            rc, out = run(['git', '-c', 'commit.gpgsign=false', 'commit', '-m', msg], d)
        if rc != 0:
            print(f'{n}: COMMIT FAIL rc={rc} :: {out[:160]}')
            continue
        _, lg = run(['git', 'log', '--format=%h %an <%ae> %s', '-1'], d)
        _, rm = run(['git', 'remote', 'get-url', 'origin'], d)
        _, br = run(['git', 'branch', '--show-current'], d)
        _, sg = run(['git', 'log', '--format=%G?', '-1'], d)
        _, st = run(['git', 'status', '-s'], d)
        print(f'OK {n}: {lg} | branch={br} | origin={rm} | 签名={sg} | 状态{"干净" if not st else "有改动"}')

if __name__ == '__main__':
    main()
