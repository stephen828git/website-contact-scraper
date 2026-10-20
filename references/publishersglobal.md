# PublishersGlobal 专用流程

此适配仅用于 `publishersglobal.com`。普通官网入口不会自动调用此流程。

## 获取公开名录

使用 Python 3.10+、`scripts/requirements-browser.txt` 和已安装的 Google Chrome；脚本开启独立无界面浏览器，不复用日常登录会话。

```powershell
# 全部国家的出版社列表及公开详情。
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/publishersglobal_scraper.py') --output './output/publishersglobal' --workers 2 --delay 2

# 仅需名录时才省略详情；list-only 不会采集全部详情联系方式。
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/publishersglobal_scraper.py') --list-only --output './output/publishersglobal'
```

脚本按国家索引 → 各国所有列表页 → 公开详情读取，排除 service-provider 资料，按出版社编号去重。当前没有国家筛选参数；用户仅要某个国家时，应在工作目录副本缩小列表任务，不能默认抓取全球再假装执行了筛选。

输出：`出版社信息.csv`、`国家覆盖检查.csv`、`异常记录.csv`、`publishers.json`。默认目录为当前工作目录 `output/publishersglobal`。公开成功页面缓存在其 `cache` 目录 7 天；`--refresh` 忽略缓存。重跑同一输出目录会更新结果，需保留旧批次时使用新目录。非零退出码也可能已经保存大量有效数据，应检查异常与覆盖情况。

网站公开联系方式卡片才作为联系方式来源；简介提到的邮箱、导航、广告及平台页脚不算。登录或会员专用字段留空并记录限制，地区不是完整邮寄地址。不能把列表采集完成解释成所有出版社都有联系方式。

## 补充已保存名录

只需基础依赖 `scripts/requirements.txt`。输入必须是前一步生成的 `publishers.json`；原始名录和补充结果分开保存。

```powershell
& $pythonExe -B -X utf8 (Join-Path $skillRoot 'scripts/publishersglobal_contacts.py') --input './output/publishersglobal/publishers.json' --seeds './publisher_websites.csv' --output './output/publishersglobal_enriched'
```

可选输入必须由当前任务明确提供，脚本不读取旧项目路径：

| 参数 | CSV 字段与含义 |
| --- | --- |
| `--seeds` | `name,country,url,source,email_domains`：已核对官网。最后一列可空，仅在有依据时以分号填写集团等其他邮箱域名 |
| `--previous` | 本工具生成的 CBL/Bienal 公司汇总，按规范化完整名称及 Brazil 国家匹配；不等于法人身份核验 |
| `--exclusions` | `name,country,value,reason`：已确认不应采用的官网候选联系方式及原因 |

名称与国家需与名录一致。`--previous` 只实现巴西目录匹配，不能传任意名录并期待通用匹配。不同编号保留不同记录。

脚本保留名录公开邮箱/电话，通过已核对 seeds、之前目录或名称本身明确写成域名的记录取得官网入口；不会联网搜索所有缺失官网，也不根据公司名字猜域名。每站最多 4 页，优先官网页脚及联系页，域名跳转需重新确认归属。外部域名邮箱及可疑电话写入待核对表，未确认前不冒充出版社自有联系方式。

官网结果缓存在输出目录 `contact_cache` 7 天；`--refresh` 重新读取，也可用于重试失败。输出为 `全球出版社名录.csv`、`已找到联系方式.csv`、`联系方式证据.csv`、`待核对联系方式.csv`、`官网抓取日志.csv` 和 `publishers_enriched.json`，默认在当前工作目录 `output/publishersglobal_enriched`。此脚本在批次结束导出，不能承诺中途中断保留所有已处理记录。

两个专用脚本都不自带 XLSX 导出。用户需要 Excel 时，从 CSV/JSON 用可用的表格能力生成，号码和字符串保持文本，保留来源、日期、覆盖检查及待核对结果；普通官网/CBL/Bienal 的 XLSX 导出不受此限制。
