"""Enrich the saved global roster using attributable public contact sources.

No domain guessing, account access, or paid services. Add independently verified
publisher websites to publisher_websites.csv (name,country,url,source).
"""
import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import tldextract
from contact_core.html_text import build_page
from contact_core.extract_emails import extract_emails
from contact_core.extract_phones import extract_phones, region_from_domain
from publishersglobal_scraper import write_csv
from scrape_contacts import fetch, site_host, normalize_url

CONTACT = re.compile(r'contact|kontakt|kontakti|contato|contacto|contatti|impressum|fale.conosco|联系我们', re.I)
EXCLUDE = re.compile(r'privacy|datenschutz|career|jobs|login|register|cart|checkout|cookie', re.I)
REGIONS = {'Brazil':'BR','United States':'US','United Kingdom':'GB','Germany':'DE','Canada':'CA',
           'Albania':'AL','Australia':'AU','France':'FR','India':'IN','Italy':'IT','Spain':'ES'}
EXTRA = ['联系方式来源','联系方式日期','匹配依据','官网检查状态']
DETAILS = ['出版社编号','出版社名称','国家或地区','类型','联系方式','来源页面','来源类型','来源日期','匹配依据']
DOMAIN = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def domain(value):
    return DOMAIN(value).top_domain_under_public_suffix


def owned_email(email, url, allowed=()):
    host = email.rpartition('@')[2].lower()
    return bool(domain(host)) and (domain(host) == domain(url) or any(host == x or host.endswith('.'+x) for x in allowed))


def norm(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value.casefold()).encode('ascii', 'ignore').decode())


def clean(value):
    return value[1:] if value.startswith(("'+", "'=", "'-", "'@")) else value


def same_site(a, b):
    return site_host(a) == site_host(b)


def crawl_site(seed, cache, refresh=False):
    key = hashlib.sha256(json.dumps({k:v for k,v in seed.items() if k != 'allowed'}, sort_keys=True).encode()).hexdigest()
    target = cache / (key + '.json')
    if target.exists() and not refresh:
        saved = json.loads(target.read_text('utf-8'))
        if time.time() - saved['timestamp'] < 7 * 86400:
            return saved
    result = {'timestamp':time.time(), 'time':datetime.now().isoformat(timespec='seconds'),
              'hits':[], 'logs':[], 'url':seed['url']}
    session = requests.Session()
    session.headers['User-Agent'] = 'Mozilla/5.0 (compatible; PublicPublisherContactResearch/1.0)'
    queue, seen = [seed['url']], set()
    start = time.monotonic()
    while queue and len(seen) < 4 and time.monotonic() - start < 55:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            page = fetch(session, url, 12, site_host(seed['url']))
            if not same_site(page.url, seed['url']):
                raise ValueError('跨域跳转，官网归属需重新核对')
            if re.search(r'domain (?:is )?for sale|buy this domain|just a moment|access denied', page.text[:1500], re.I):
                raise ValueError('停放域名或访问验证页')
            # Contact-page body and home-page footer only: avoid author/review emails.
            on_contact = bool(CONTACT.search(urlsplit(url).path))
            if on_contact:
                scope = page
            else:
                pieces = page.soup.select('footer, [role="contentinfo"]')
                scope = build_page(page.url, ''.join(str(p) for p in pieces))
            region = REGIONS.get(seed['country']) or region_from_domain(site_host(url))
            for kind, hits in [('邮箱',extract_emails(scope)),('电话',extract_phones(scope, region=region))]:
                for hit in hits:
                    result['hits'].append([kind,hit['value'],page.url])
            result['logs'].append([url,'成功'])
            for a in page.anchors:
                linked = a['resolved']
                if not linked or not linked.startswith(('https://','http://')):
                    continue
                if same_site(linked,seed['url']) and CONTACT.search(linked+' '+a['text']) and not EXCLUDE.search(linked):
                    if linked not in seen and linked not in queue:
                        queue.append(linked)
            if queue:
                time.sleep(0.8)
        except (requests.RequestException,ValueError,UnicodeError) as exc:
            result['logs'].append([url,str(exc)[:250]])
    session.close()
    result['hits'] = [list(x) for x in dict.fromkeys(tuple(x) for x in result['hits'])]
    target.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return result


def enrich(args):
    data = json.loads(args.input.read_text('utf-8-sig'))
    records = data['records']
    for row in records:
        for h in EXTRA:
            row[h] = ''
        row['联系方式状态'] = '尚无公开联系方式；官网待核实'
    indexed = defaultdict(list)
    for r in records:
        indexed[(norm(r['出版社名称']),r['国家或地区'])].append(r)
    details, seeds, review = [], {}, []

    def add(row, kind, value, source, source_type, date, basis):
        if value:
            details.append([row['出版社编号'],row['出版社名称'],row['国家或地区'],kind,clean(value),source,source_type,date,basis])

    def seed(row, url, source, basis, allowed=''):
        try:
            url = normalize_url(url)
        except ValueError:
            return
        key = (url,row['国家或地区'])
        job = seeds.setdefault(key, {'url':url,'country':row['国家或地区'],'rows':[],'source':source,'basis':basis,'allowed':[]})
        job['allowed'] = sorted(set(job['allowed'] + [x.strip().lower() for x in allowed.split(';') if x.strip()]))
        if row['出版社编号'] not in job['rows']:
            job['rows'].append(row['出版社编号'])
        row['官网'] = url
        row['匹配依据'] = basis

    for r in records:
        for kind in ('邮箱','电话'):
            for value in r.get(kind,'').splitlines():
                add(r,kind,value,r['资料来源'],'PublishersGlobal公开字段',r['抓取时间'],'原资料页明确公开')
    if args.previous and args.previous.exists():
        old = list(csv.DictReader(args.previous.open(encoding='utf-8-sig',newline='')))
        for prior in old:
            if prior.get('国家') not in ('Brasil','Brazil','BR',''):
                continue
            for r in indexed.get((norm(prior['公司名称或网站标题']),'Brazil'),[]):
                basis = '巴西目录公司名称规范化完全一致；未经人工法人核验'
                for kind in ['邮箱','电话']:
                    for value in prior.get(kind,'').splitlines():
                        add(r,kind,value,prior['目录来源'],prior['目录类型'],prior['抓取时间'],basis)
                if prior.get('网站'):
                    domains = ';'.join(v.rpartition('@')[2] for v in prior.get('邮箱','').splitlines() if '@' in v)
                    seed(r,prior['网站'],prior['目录来源'],basis,domains)
    for r in records:
        name = r['出版社名称'].strip()
        # ASCII domains only. A dotted company name is not automatically a domain.
        if re.fullmatch(r'(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.(?:com|org|net|info|biz|am|be|de|fr|it|es|nl|uk|ca|au|in|br|co|nz|za)',name):
            seed(r,'https://'+name,r['资料来源'],'目录中的出版社名称即域名；仅接受同域公开联系页')
    if args.seeds and args.seeds.exists():
        for s in csv.DictReader(args.seeds.open(encoding='utf-8-sig',newline='')):
            for r in indexed.get((norm(s['name']),s['country']),[]):
                seed(r,s['url'],s['source'],'名称、国家与官网公开信息人工核对',s.get('email_domains','') or '')
    cache = args.output / 'contact_cache'
    cache.mkdir(parents=True,exist_ok=True)
    by_id = {r['出版社编号']:r for r in records}
    exclusions = {}
    if args.exclusions and args.exclusions.exists():
        for x in csv.DictReader(args.exclusions.open(encoding='utf-8-sig',newline='')):
            exclusions[(norm(x['name']),x['country'],x['value'])] = x['reason']
    jobs = list(seeds.values())
    print(f'名录 {len(records)} 条；已有目录联系方式 {len(details)} 条；官网任务 {len(jobs)} 个',flush=True)
    log = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(crawl_site,s,cache,args.refresh):s for s in jobs}
        for number,future in enumerate(as_completed(pending),1):
            s = pending[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {'hits':[], 'logs':[[s['url'],str(exc)]], 'time':datetime.now().isoformat(timespec='seconds')}
            for identifier in s['rows']:
                r = by_id[identifier]
                success = sum(x[1]=='成功' for x in result['logs'])
                r['官网检查状态'] = f'读取{success}页；候选{len(result["hits"])}条（含待核对项）' if success else '读取失败，待重试'
                for kind,value,url in result['hits']:
                    reason = exclusions.get((norm(r['出版社名称']),r['国家或地区'],value))
                    if reason:
                        review.append([identifier,r['出版社名称'],r['国家或地区'],value,url,reason])
                    elif kind == '电话' and (value.endswith('12345') or any(k=='电话' and v != value and v.startswith(value) for k,v,u in result['hits'])):
                        review.append([identifier,r['出版社名称'],r['国家或地区'],value,url,'疑似占位号码或另一号码的截断片段；待人工核对'])
                    elif kind == '邮箱' and not owned_email(value,s['url'],s['allowed']):
                        review.append([identifier,r['出版社名称'],r['国家或地区'],value,url,'外部域名；可能属于集团、代理商或服务商，未归入出版社邮箱'])
                    else:
                        add(r,kind,value,url,'官网公开页（用途请查来源）',result['time'],s['basis'])
                log.extend([identifier,r['出版社名称'],u,status] for u,status in result['logs'])
            if number % 10 == 0 or number == len(jobs):
                print(f'官网任务 {number}/{len(jobs)}；累计联系方式证据 {len(details)} 条',flush=True)
    details = [list(x) for x in dict.fromkeys(tuple(x) for x in details)]
    per_id = defaultdict(list)
    for d in details:
        per_id[d[0]].append(d)
    for r in records:
        evidence = per_id.get(r['出版社编号'], [])
        for kind in ['邮箱','电话']:
            r[kind] = '\n'.join(sorted({d[4] for d in evidence if d[3]==kind}))
        if evidence:
            r['联系方式状态'] = '已找到公开联系方式；未验证可达性'
            r['联系方式来源'] = '\n'.join(sorted({d[5] for d in evidence}))
            r['联系方式日期'] = '\n'.join(sorted({d[7][:10] for d in evidence}))
            r['匹配依据'] = '\n'.join(sorted({d[8] for d in evidence}))
        elif r['官网检查状态']:
            r['联系方式状态'] = '本次未取得联系方式；见官网检查状态'
    for c in data['coverage']:
        if c[2] == c[3] and c[1] != c[2]:
            c[4] = '列表已遍历；国家索引计数不一致'
        elif c[2] != c[3]:
            c[4] = '已遍历缓存列表；唯一条目少于声明数量，待复核'
    data['fields'] = list(dict.fromkeys(data['fields']+EXTRA))
    data['contact_details'] = details
    data['contact_headers'] = DETAILS
    data['contact_logs'] = log
    data['review_contacts'] = [list(x) for x in dict.fromkeys(tuple(x) for x in review)]
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'publishers_enriched.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    for name,rs in [('全球出版社名录',records),('已找到联系方式',[r for r in records if r['邮箱'] or r['电话']])]:
        write_csv(args.output/(name+'.csv'),data['fields'],[[r.get(h,'') for h in data['fields']] for r in rs])
    write_csv(args.output/'联系方式证据.csv',DETAILS,details)
    write_csv(args.output/'待核对联系方式.csv',['出版社编号','出版社名称','国家或地区','候选联系方式','来源页面','原因'],data['review_contacts'])
    write_csv(args.output/'官网抓取日志.csv',['出版社编号','出版社名称','页面','结果'],log)
    print(json.dumps({'roster':len(records),'contact_publishers':len(per_id),'contact_countries':len({by_id[i]['国家或地区'] for i in per_id}),'website_jobs':len(jobs),'evidence':len(details)},ensure_ascii=False),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True,help='专用名录脚本生成的 publishers.json')
    p.add_argument('--previous',type=Path,help='可选，已核对的 CBL/Bienal 公司汇总 CSV')
    p.add_argument('--seeds',type=Path,help='可选，已核实官网清单 CSV')
    p.add_argument('--exclusions',type=Path,help='可选，已确认错误联系方式 CSV')
    p.add_argument('--output',type=Path,default=Path.cwd()/'output/publishersglobal_enriched')
    p.add_argument('--workers',type=int,choices=range(1,5),default=4)
    p.add_argument('--refresh',action='store_true')
    args = p.parse_args()
    for key in ('input', 'previous', 'seeds', 'exclusions'):
        value = getattr(args, key)
        if value is not None and not value.is_file():
            p.error(f'--{key} 文件不存在：{value}')
    enrich(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
