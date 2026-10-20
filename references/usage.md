# 普通网站运行说明

## 环境与调用

Python 3.10+。先实际运行候选解释器的 `--version`；Windows 的 `python` 可能只是不可执行的商店别名，可检查当前项目 `.venv/Scripts/python.exe`、`py` 或已安装的 Python 环境。避免把本机特有的解释器路径写成技能的必需条件。

缺依赖时在任务目录创建虚拟环境，并用该环境的 Python 安装 `scripts/requirements.txt`。Bienal/CBL 改用 `scripts/requirements-directories.txt`；PublishersGlobal 浏览器读取改用 `scripts/requirements-browser.txt`，且机器需要已安装 Google Chrome。两种专用模式的依赖互不强制安装。不要在技能目录创建 `.venv` 或安装浏览器。

以下 PowerShell 中 `$skillRoot` 是已读取的 SKILL.md 所在绝对目录，`$pythonExe` 是已经验证可运行的 Python 路径；保持当前目录为任务目录。其他系统使用对应的 shell 写法。

```powershell
# 用真实路径设置变量后执行，网址换成用户给定的地址。
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/scrape_contacts.py') 'https://example.com' -o './output/contacts'

# websites.txt 每行一个网址，空行和 # 开头行忽略；支持 UTF-8 BOM。
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/scrape_contacts.py') -i './websites.txt' -o './output/contacts'

# 国家已知时帮助解析无国际区号的本地电话。
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/scrape_contacts.py') -i './websites.txt' --region CN --max-pages 40 --depth 3 --delay 1
```

也可同时传入多个位置参数网址。不传网址和 `-i` 会进入交互输入，自动化调用应始终传入输入。`--input` 只接受网址 TXT，不接受 CSV、XLSX 或目录 JSON。

## 参数与行为

| 参数 | 默认或作用 |
| --- | --- |
| `-o / --output` | 当前工作目录 `output/website-contacts`；每次运行新建时间戳子目录 |
| `--max-pages` | 每站最多尝试 20 页，包括失败页 |
| `--depth` | 链接深度 2；首页深度 0 |
| `--delay` | 普通网站页面间隔 0.5 秒，支持 0–60 |
| `--timeout` | 每次连接/读取 15 秒 |
| `--site-timeout` | 每站调度预算 120 秒，开始下一页前检查；不是严格墙钟超时 |
| `--region` | ISO 两位电话国家代码，如 CN、BR、GB；缺省尝试从域名推断 |
| `--csv-only` | 只生成 CSV，可在没有 openpyxl 时使用 |
| `--generic` | 禁用 Bienal/CBL 目录识别，仅在确实需要普通网站逻辑时使用 |

联系、关于、支持页优先；首个页面可跟随跨域跳转，之后只遍历最终主机，将 www 和无 www 视为同站，不遍历其他子域名或社交平台。每页最多 3 MB，不下载 PDF、图片等附件。需要子域名联系方式时将对应子域作为独立输入。

默认读取服务器返回的 HTML，不执行 JavaScript。邮箱反混淆、Cloudflare 邮箱编码、电话号码校验和社交链接规范化复用 `contact_core`。明显示例邮箱和 noreply 等可能被规则过滤。地址仅来自结构化数据和 HTML address 标签，公司名优先结构化数据，否则网站标题。

## 输出与核对

- `联系方式.xlsx`：公司汇总、联系方式明细、抓取日志三个工作表，冻结表头、筛选；国际电话及抓取字符串按文本写入。
- `公司汇总.csv`：每个普通网站一行；目录模式每个目录主体一行。列包括名称、邮箱、电话、社交、地址、状态、备注、时间及目录扩展字段。
- `联系方式明细.csv`：联系方式与来源页面一行；同一联系方式有多个来源时保留多行，汇总字段去重。
- `抓取日志.csv`：成功、失败、停止原因。

CSV 使用 UTF-8 BOM，对公式形式的文本加前导单引号；电话等文本优先使用 XLSX。不要为了去掉 CSV 单引号而损坏公式保护或国际区号。

每完成一个普通网站保存 CSV，批次结束生成 Excel。Ctrl+C 保存此前完整网站，正在抓取的网站不保证保留。普通模式没有页面缓存；目录模式的缓存与恢复见对应参考。

普通模式只要至少有一个网站读取成功，退出码就可能为 0，因此必须检查各行状态、日志和联系方式字段。先统计网站总数、成功读取数、至少有邮箱/电话/其他联系方式的数量，再报告缺失与失败。抽查来源页面时区分企业联系人、作者、外包商与平台自身联系方式；成功读取不代表已查全。
