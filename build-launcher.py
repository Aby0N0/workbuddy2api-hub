# -*- coding: utf-8 -*-
"""用 Windows 自带的 C# 编译器把启动器编译成 exe，并把图标嵌进去。

为什么不用 PyInstaller 之类：那些要下载几百 MB 的东西。
Windows 自带 csc.exe（C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe），
直接就能编出一个几十 KB 的 .NET exe，不用装任何东西、不联网。

用法：python build_launcher.py <工作目录> <结果.json>
"""
import json
import os
import subprocess
import sys
import traceback

CSC_CANDIDATES = [
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
]

CS_NAME = "WorkBuddyLauncher.cs"
ICO_NAME = "workbuddy.ico"
EXE_NAME = "launcher.exe"


def main():
    work = os.path.abspath(sys.argv[1])
    result_path = os.path.abspath(sys.argv[2])
    log_path = os.path.join(work, "build_log.txt")
    try:
        csc = next((p for p in CSC_CANDIDATES if os.path.isfile(p)), None)
        if csc is None:
            raise RuntimeError("找不到系统自带的 csc.exe（.NET Framework 4.x 的 C# 编译器）")

        cs = os.path.join(work, CS_NAME)
        ico = os.path.join(work, ICO_NAME)
        exe = os.path.join(work, EXE_NAME)
        for need in (cs, ico):
            if not os.path.isfile(need):
                raise RuntimeError("缺少输入文件：%s" % need)

        args = [
            csc, "/nologo", "/target:winexe", "/platform:anycpu", "/optimize+",
            "/win32icon:" + ico,
            "/out:" + exe,
            cs,
        ]

        # 输出重定向到文件而不是管道：受限环境下开管道可能被直接拒绝，
        # 而且管道会让"没输出"和"出错了"长得一模一样。
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.run(args, cwd=work, stdout=log,
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            log_text = fh.read()

        payload = {
            "ok": proc.returncode == 0 and os.path.isfile(exe),
            "compiler": csc,
            "returncode": proc.returncode,
            "exe": exe,
            "exe_bytes": os.path.getsize(exe) if os.path.isfile(exe) else 0,
            "log": log_text.strip(),
        }
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ok"] else 1
    except Exception as exc:
        payload = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
