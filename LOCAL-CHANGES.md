# 本地定制说明（Aby0N0 的 fork）

这份文件只记录**这个 fork 在上游基础上改了哪些自用的东西、为什么改、
以及以后合并上游时哪里可能冲突**。跟上游无关，上游不会看它。

> 上游仓库：`ardeyouxipianyi/workbuddy2api-hub`
>
> **合并上游请双击 `update-from-upstream.bat`。**
> **不要点 GitHub 上的 "Sync fork"** —— 那会把下面这些改动冲掉。

## 1. 面板密码改成 7 天免登录（cookie 会话 + 落盘）

**改了什么**：面板登录成功后，除了原来的请求头令牌，再下发一个 `HttpOnly` cookie
（有效期 7 天）。并且把令牌账本**落到磁盘**，所以**网关重启也不用重新输密码**。

**这 7 天从"登录那一刻"起算，不因重启而重置**，也不是永久 —— 第 8 天照样要重新登录。
账本文件 `panel-sessions.json` 里**只存令牌的 SHA-256 摘要，不存原文**，
所以文件泄露也拿不去登录；删掉这个文件 = 所有浏览器重新登录。

**改了哪些文件**

| 文件 | 改了什么 |
|---|---|
| `wb_settings.py` | `PanelSessions` 支持落盘（`path=` 参数）、只存摘要、损坏文件不致命 |
| `wb_proxy.py` | 新增 `PANEL_SESSIONS_FILE`（可用 `WB_PROXY_PANEL_SESSIONS_FILE` 覆盖），构造时传进去 |
| `tests/_test_panel_cookie_session.py` | 从 28 项扩到 45 项：新增令牌账本单测 + **真起第二个网关进程**验证重启后免登录 |
| `tests/_isolated_dirs.py` | 隔离目录里加上会话文件 |
| `tests/_test_pricing_panel_auth.py` | 补上它本来就该有的 `isolated_data_dirs()` 调用（上游漏了：只 import 没调用，于是它跑在真实数据目录上，会往仓库里写令牌） |
| `tests/_test_connection_reuse.py`、`tests/_test_usage_etag_cache.py`、`tests/_mobile_check.py` | 各自启动网关时把会话文件指向自己的临时目录 |
| `.gitignore` | 忽略 `panel-sessions.json` |
| `README.md` | 面板密码那段（原来写着"重启后会话全清"） |

**合并上游时的冲突风险**：`wb_settings.py`（`PanelSessions` 类）、`wb_proxy.py`
（`PANEL` 那几行）、`README.md`（同一句话）、以及那几个测试文件里各自一行的
`env=dict(...)` / `isolated_data_dirs(...)`。

## 2. 界面配色：不再本地定制，改用上游自带的调色台

**历史**：曾用"在 `dashboard.html` 样式表末尾追加一段覆盖"的办法，把配色从上游的
暖色调改回旧版的蓝灰。**这段覆盖已在合并上游 v1.7.31 时删除** —— 原因见下。

**现在**：上游自带了完整的调色功能，比自己改样式表更合适：

- 入口：右上角**主题菜单 →「色彩配置」**
- 可调 **11 项**：强调色、成功色、警告色、错误色、主按钮字、页面底、卡片、
  内嵌块、主文字、次文字、边框
- 改动**实时生效**，并写入浏览器 `localStorage`（**刷新后保留**）
- 每一行都显示文字对比度，低于 4.5 会标黄提醒
- 有「重置」（恢复出厂值）和「导出 JSON」

所以想让界面好看，**在面板里点几下就行，不用改代码**。

**合并上游时的冲突风险**：无（`dashboard.html` 现在与上游逐字节一致）。

> 注：上游在 v1.7.31 又把默认配色校正过一次（强调色 `#c96442` → `#a14427`，
> 为了对比度），所以现在的默认色既不是更早的陶土红，也不是我当年覆盖的蓝灰。

## 3. 一键更新脚本

- `update-from-upstream.py` / `update-from-upstream.bat`

双击 `.bat` 后它会：检查有没有未提交的改动 → 取上游最新版 →
**列出更新内容让你确认** → 合并 → 跑一遍测试 → 问要不要推送到 fork。
**遇到冲突会立刻放弃合并**（不留半成品），并打印一句可以直接发给 AI 的话。

**合并上游时的冲突风险**：无（上游没有这两个文件）。

## 4. 带图标的最小化启动器

- `WorkBuddy 网关.exe` —— 双击它 = 用**最小化**的方式启动 `start-wb-proxy.bat`。
  图标已内嵌在 exe 里；外壳编译成图形程序（`/target:winexe`），
  **不分配控制台，所以不闪黑框**。它**不替代** `start-wb-proxy.bat`，只是调用它 ——
  上游以后更新那个 bat，这个 exe 不用重新编译。
- `WorkBuddyLauncher.cs` —— 那个 exe 的**全部源码**（约 100 行 C#）。
- `build-launcher.py` —— 编译命令：调用 Windows 自带的
  `csc.exe`（`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`），
  **不联网、不下载任何东西**，产物约 285KB（绝大部分是图标）。
- `workbuddy.ico` —— 图标原件（exe 里已内嵌一份，这份备用）。

想换图标：把新的 `.ico` 命名为 `workbuddy.ico`，然后

```
python build-launcher.py . build-result.json
```

把生成的 `launcher.exe` 复制到仓库根目录、改名成 `WorkBuddy 网关.exe` 即可。

**合并上游时的冲突风险**：无。

## 上游更新时要注意

`start-wb-proxy.bat` 是上游的文件。上游更新它时**直接接受上游版本**就行 ——
启动器 exe 只是调用它，不依赖它里面的具体内容。
