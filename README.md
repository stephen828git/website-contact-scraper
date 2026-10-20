# Website Contact Scraper

一个可安装到 Codex 的网站公开联系方式采集 skill，也可以直接作为 Python 命令行工具运行。

提取公司名称、官网、邮箱、电话、社交链接及网页明确提供的地址，保留来源页面，导出 Excel / CSV。适合单个官网、网址清单、展会展商及企业目录的联系方式整理。

English: A reusable Codex skill and Python CLI for collecting public business contact information, with source URLs and spreadsheet exports. It does not require a paid contact database or API key.

## 下载与安装

需要 Python 3.10 或更新版本。普通网页模式无需浏览器；可选的 PublishersGlobal 适配需要 Google Chrome。

### 安装到 Codex

将整个仓库放入个人 skills 目录，文件夹名保持为 `website-contact-scraper`。

Windows PowerShell：

```powershell
$skillsDir = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex/skills' }
New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
git clone https://github.com/stephen828git/website-contact-scraper.git (Join-Path $skillsDir 'website-contact-scraper')
```

macOS / Linux：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/stephen828git/website-contact-scraper.git "${CODEX_HOME:-$HOME/.codex}/skills/website-contact-scraper"
```

也可以使用 GitHub 的 **Code → Download ZIP**。解压后将 `website-contact-scraper-main` 重命名为 `website-contact-scraper`，放进上述目录。应能在 `website-contact-scraper/SKILL.md` 找到入口文件；不要多套一层目录。

如果同名 skill 已存在，先备份，再根据需要更新，避免覆盖自己的修改。

在 Codex 中开始新对话，输入：

```text
$website-contact-scraper 抓取 https://example.com 的公司名、官网和公开联系邮箱，保留来源，导出 Excel。
```

```text
$website-contact-scraper 根据 websites.txt 中的网址批量采集公开联系方式。没有找到邮箱的记录也保留，并注明读取失败或未检出。
```

```text
$website-contact-scraper 抓取这个展会目录中每家公司的名称、官网及邮箱。先检查目录分页和公司字段归属，再补充公司官网联系方式。
```

`example.com` 只是示例地址，请替换成实际目标。新目录需要先适配页面结构；并非任意展会链接都可以直接运行现有目录解析器。

### 直接运行 Python

不使用 Codex 也可以运行。克隆仓库后，在一个单独的任务目录创建虚拟环境、安装依赖，将输出保存在任务目录。

以下命令中的路径需替换为实际安装位置。

Windows PowerShell：

```powershell
$skillRoot = 'C:/path/to/website-contact-scraper'
py -3 -m venv .venv
$pythonExe = Join-Path (Get-Location) '.venv/Scripts/python.exe'
& $pythonExe -m pip install -r (Join-Path $skillRoot 'scripts/requirements.txt')
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/scrape_contacts.py') 'https://example.com' -o './output/contacts'
```

macOS / Linux：

```bash
skill_root='/path/to/website-contact-scraper'
python3 -m venv .venv
.venv/bin/python -m pip install -r "$skill_root/scripts/requirements.txt"
.venv/bin/python -B -X utf8 "$skill_root/scripts/scrape_contacts.py" 'https://example.com' -o './output/contacts'
```

批量输入：`websites.txt` 每行一个网址，然后用 `-i websites.txt` 替换位置参数网址。查看全部参数：

```bash
python -B -X utf8 /path/to/website-contact-scraper/scripts/scrape_contacts.py --help
```

## 支持范围

| 输入 | 现有能力 | 依赖 |
| --- | --- | --- |
| 单个或多个公司官网 | 同站 HTML 抓取，优先联系页、关于页与支持页 | `scripts/requirements.txt` |
| UTF-8 网址 TXT | 按网址批量抓取，可包含 BOM、空行及注释 | 同上 |
| Bienal São Paulo / CBL | 专用展商、会员目录解析与分页 | `scripts/requirements-directories.txt` |
| PublishersGlobal | 专用公开名录采集，及基于已核实官网的联系方式补充 | 名录使用 `scripts/requirements-browser.txt`；官网补充使用基础依赖 |
| 其他展会或动态目录 | Codex 检查结构后在任务目录编写适配 | 按目标网站决定 |

普通模式默认每站最多尝试 20 页、深度 2、页面间隔 0.5 秒。服务器返回的 HTML 不包含动态内容时，需要另行处理，普通模式不会自动执行 JavaScript。

## 输出与限制

普通官网、CBL 和 Bienal 模式生成：

- `联系方式.xlsx`：公司汇总、联系方式明细、抓取日志。
- `公司汇总.csv`、`联系方式明细.csv`、`抓取日志.csv`：UTF-8 BOM 编码。
- 每条联系方式保留实际来源页面。CSV 对可能被表格软件解释为公式的文本做保护。

PublishersGlobal 专用脚本输出 CSV / JSON，默认不生成 XLSX。具体字段与恢复方式见 [PublishersGlobal 说明](references/publishersglobal.md)。

邮箱为空表示本次未取得，不表示公司没有邮箱。成功读取网页不代表全站抓取完成；提取到邮箱不代表已核实公司归属或可投递性。目录主体与平台页脚联系方式必须区分，共用网站或同名记录不能直接认定为同一法人。

仅用于公开联系方式采集。遇到持续拒绝访问、验证码、登录或会员限制时保留结果与原因，不绕过访问控制。工具不发送邮件、消息或联系表单。请遵守目标网站的访问规则及适用要求。

## 开发与测试

测试使用本地模拟页面，不需要真实爬取网站，也不会发送消息。

```bash
python -m pip install -r scripts/requirements-directories.txt -r scripts/requirements-browser.txt
cd scripts
python -B -X utf8 -m unittest discover -p 'test_*.py' -v
```

详细运行方式见 [普通网站说明](references/usage.md) 和 [目录与动态网站说明](references/directories.md)。修改目录适配时请保留来源、覆盖检查、未知值及失败状态。

发布仓库只包含代码、说明和合成测试数据，不包含实际采集名单、网页缓存、账号凭据或个人机器配置。提交问题时也请移除这些内容。

## 许可证与来源

本项目采用 [MIT License](LICENSE)。`scripts/contact_core/` 中的提取模块源自 [omkarcloud/website-email-contact-scraper](https://github.com/omkarcloud/website-email-contact-scraper)，保留其版权和许可声明。来源及修改范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
