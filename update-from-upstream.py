#!/usr/bin/env python3
"""一键把原作者的最新版合并进来，同时保住你自己的改动。

用法（Windows 双击 update-from-upstream.bat，或在仓库目录里跑）：
    python update-from-upstream.py

它按顺序做这几件事，每一步失败都停在原地、不改坏仓库：

  1. 检查有没有「合并做了一半」或「有未提交的改动」——有就先停，让你找 AI；
  2. 记下当前提交号并打印出来（万一要回退，这就是后悔药）；
  3. 联网取原作者最新版；
  4. 没有新东西 → 打印「已经是最新」并退出；
  5. 有新的 → 合并。
       合并干净 → 跑一遍测试套件 → 问你要不要推送到你自己的 fork；
       有冲突   → 立刻放弃这次合并（仓库保持原样、网关不受影响），
                  并打印一段可以直接发给 AI 的说明。

这个脚本本身是「本地工具」，没有提交进仓库，也不会被 git 看见。
"""
import os
import subprocess
import sys

try:  # 控制台编码兜底：宁可显示成问号，也不要因为一个字符崩掉
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

# 已知的、与本次更新无关的失败（上游测试套件自身的隔离漏洞：
# 它起的子进程读到真实 accounts/ 目录，与你仓库里有没有真实账号有关）。
KNOWN_FLAKY = {
    "_test_analytics_hour_buckets.py",
    "_test_usage_aggregate_cache.py",
    "_test_usage_day_buckets.py",
    "_test_usage_hour_buckets.py",
    "_test_usage_series_minutes.py",
}


def run(*args, **kwargs):
    return subprocess.run(list(args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kwargs)


def say(text=""):
    print(text, flush=True)


def stop(message, code=1):
    say()
    say("=" * 62)
    say(message)
    say("=" * 62)
    input("\n按回车键关闭…")
    sys.exit(code)


def git(*args):
    return run("git", *args)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    if not os.path.isdir(os.path.join(here, ".git")):
        stop("这个脚本要放在仓库目录里（和 wb_proxy.py 同一层）才能用。")

    say("仓库：%s" % here)

    # 1) 安全闸：合并做了一半 / 有未提交的改动
    if os.path.exists(os.path.join(here, ".git", "MERGE_HEAD")):
        stop("检测到上一次合并还没收尾。请把下面这句发给 AI，让它来处理：\n"
             "  我的仓库里有一次没收尾的合并，帮我处理一下")
    dirty = git("status", "--porcelain").stdout.strip()
    if dirty:
        say()
        say("!! 你有还没提交的改动，脚本不敢动（怕弄丢）：")
        for line in dirty.splitlines()[:20]:
            say("   " + line)
        stop("先把这些改动处理掉（提交或还原），或者直接找 AI 帮你。")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        stop("当前不在 main 分支上（现在在 %s）。先切回 main 再跑这个脚本。" % branch)

    before = git("rev-parse", "--short", "HEAD").stdout.strip()
    say("当前提交：%s" % before)
    say("后悔药：万一要回到现在这个状态，把下面这行发给 AI 就行")
    say("   git reset --hard %s" % before)

    # 2) 取上游最新版
    say()
    say("正在联网获取原作者的最新版…")
    fetched = git("fetch", "origin", "--prune")
    if fetched.returncode != 0:
        stop("联网取最新版失败，通常是网络问题。原始信息：\n%s" % fetched.stderr.strip())

    behind = git("rev-list", "--count", "HEAD..origin/main").stdout.strip() or "0"
    if behind == "0":
        say()
        say("已经是最新版，什么都不用做。")
        input("\n按回车键关闭…")
        return 0

    say()
    say("原作者有 %s 个新提交，先看看都是什么：" % behind)
    log = git("log", "--oneline", "--no-decorate", "HEAD..origin/main").stdout
    for line in log.splitlines()[:25]:
        say("   " + line)
    if len(log.splitlines()) > 25:
        say("   …（还有 %d 条）" % (len(log.splitlines()) - 25))

    say()
    answer = input("现在合并进来？(y = 合并 / 其他 = 退出) ").strip().lower()
    if answer != "y":
        say("已取消，什么都没动。")
        return 0

    # 3) 合并
    say()
    say("正在合并…")
    merged = git("merge", "origin/main", "--no-edit")
    if merged.returncode != 0:
        say(merged.stdout.strip())
        say(merged.stderr.strip())
        # 放弃这次合并：仓库回到你原来的状态，网关照常能用
        git("merge", "--abort")
        stop("这次合并撞上了「冲突」——两边的改动落在同一行，机器不敢自己拿主意。\n"
             "已经帮你放弃这次合并，你的仓库和网关都没受影响。\n\n"
             "把下面这段发给 AI，让它来解（它上次干过，很快）：\n"
             "   帮我合并上游 origin/main，有冲突你解一下，解完跑一遍测试\n\n"
             "（顺带把上面 git 打印的那几行一起发过去更好）")

    after = git("rev-parse", "--short", "HEAD").stdout.strip()
    say("合并成功：%s -> %s" % (before, after))

    # 4) 跑测试
    say()
    say("正在跑测试套件（大约 1 分钟）…")
    tests = run(sys.executable, os.path.join(here, "tests", "run_all.py"))
    tail = (tests.stdout or "").strip().splitlines()
    summary = [l for l in tail if "passed," in l or "failed:" in l]
    for line in summary:
        say("   " + line.strip())
    failed = [l for l in tail if l.strip().startswith("[FAIL]")]
    real = [l for l in failed
            if not any(name in l for name in KNOWN_FLAKY)]
    if real:
        say()
        say("!! 有测试失败，而且不是已知的那 5 个：")
        for line in real:
            say("   " + line.strip())
        say("把上面这几行发给 AI 看看。")
    else:
        say("测试通过（那 5 个用量缓存套件失败是上游测试自身的隔离问题，与你的改动无关，可以忽略）。")

    # 5) 推送到自己的 fork
    say()
    if git("remote").stdout.split().count("fork") == 0:
        say("没有配置 fork 远程地址，跳过推送。")
    else:
        answer = input("推送到你自己的 fork（%s）？(y/n) " % "Aby0N0/workbuddy2api-hub").strip().lower()
        if answer == "y":
            pushed = git("push", "fork", "main")
            say(pushed.stdout.strip() or pushed.stderr.strip())
            if pushed.returncode == 0:
                say("已推送。")
            else:
                say("推送失败，把上面的信息发给 AI。")
        else:
            say("没有推送。本地已经是合并好的状态，随时可以再推。")

    say()
    say("全部完成。别忘了关掉网关窗口、重新双击 start-wb-proxy.bat 让它用上新代码。")
    input("\n按回车键关闭…")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say("\n已中断，什么都没动。")
        sys.exit(130)
