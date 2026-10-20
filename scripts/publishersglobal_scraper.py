"""PublishersGlobal public publisher directory; resume cached pages safely."""
import argparse
import csv
import hashlib
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote

from bs4 import BeautifulSoup
from directory_scraper import explicit_emails

ORIGIN = 'https://www.publishersglobal.com'
COUNTRIES = ORIGIN + '/directory/list-countries-publishers'
PROFILE_PATH = re.compile(r'^/directory/publisher-profile/(\d+)/?$')
COUNTRY_PATH = re.compile(r'^/directory/([^/]+)/publishers-in-([^/]+)/?$')
FIELDS = ['出版社名称', '国家或地区', '城市或州', '官网', '邮箱', '电话', '地址',
          '出版类别', '出版形式', '出版语言', '简介', '详细介绍', '联系方式状态',
          '地址状态', '资料页状态', '出版社编号', '资料来源', '目录来源', '抓取时间']


def soup_main(text):
    soup = BeautifulSoup(text, 'html.parser')
    if not soup.find('h1'):
        raise ValueError('页面没有标题，可能是验证页或结构已变化')
    return soup, soup.select_one('main main') or soup.find('main') or soup


def parse_countries(text):
    _, main = soup_main(text)
    countries = {}
    for anchor in main.select('a.nav-vertical-link-flex[href]'):
        match = COUNTRY_PATH.fullmatch(urlsplit(anchor['href']).path)
        badge = anchor.select_one('.count-badge')
        if not match or not badge:
            continue
        spans = anchor.find_all('span', recursive=False)
        country = spans[0].get_text(' ', strip=True)
        count = int(re.sub(r'\D', '', badge.get_text()))
        source = urljoin(ORIGIN, anchor['href'])
        if urlsplit(source).hostname != 'www.publishersglobal.com':
            continue
        countries[source] = {'country': country, 'count': count, 'url': source}
    if not countries:
        raise ValueError('没有找到国家/地区出版社列表')
    return list(countries.values())


def parse_listing(text, country, source, stamp):
    _, main = soup_main(text)
    records = []
    for card in main.select('.entity-card'):
        anchor = card.select_one('a.entity-card-name[href]')
        if not anchor:
            continue
        profile = urljoin(ORIGIN, anchor['href'])
        match = PROFILE_PATH.fullmatch(urlsplit(profile).path)
        if not match or urlsplit(profile).hostname != 'www.publishersglobal.com':
            continue  # Supplier links are never publisher records.
        name = anchor.get_text(' ', strip=True)
        location = card.select_one('.entity-card-meta')
        brief = card.select_one('.entity-card-brief')
        row = dict.fromkeys(FIELDS, '')
        row.update({'出版社名称': name, '国家或地区': country,
                    '城市或州': location.get_text(' ', strip=True) if location else '',
                    '简介': brief.get_text(' ', strip=True) if brief else '',
                    '出版社编号': match.group(1), '资料来源': profile, '目录来源': source,
                    '资料页状态': '待读取', '抓取时间': stamp})
        records.append(row)
    totals = re.findall(r'(?:of|Browse)\s+([\d,]+)\s', main.get_text(' ', strip=True))
    page_match = re.search(r'Page\s+(\d+)\s+of\s+(\d+)', main.get_text(' ', strip=True))
    pages = int(page_match.group(2)) if page_match else 1
    number = int(page_match.group(1)) if page_match else 1
    # Prefer structured total if present. It represents all results, not page length.
    expected = None
    soup = BeautifulSoup(text, 'html.parser')
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or script.get_text())
            if isinstance(data, dict) and data.get('@type') == 'ItemList':
                expected = int(data['numberOfItems'])
        except (ValueError, KeyError, TypeError):
            pass
    if expected is None and totals:
        expected = int(totals[0].replace(',', ''))
    if not records and expected != 0:
        raise ValueError('未找到出版社卡片，不能把该页判为抓取成功')
    return records, {'pages': pages, 'page': number, 'total': expected}


def parse_profile(text, row, stamp):
    soup, main = soup_main(text)
    heading = main.find('h1')
    if not heading or heading.get_text(' ', strip=True).casefold() in ('just a moment...', 'access denied'):
        raise ValueError('资料页未正常加载')
    # The page title is authoritative; preserve the directory name in the brief/source.
    row = dict(row)
    row['出版社名称'] = heading.get_text(' ', strip=True)
    location = heading.parent.find('p', recursive=False)
    if location:
        row['城市或州'] = location.get_text(' ', strip=True)
    for field, prefix in [('出版类别', '/directory/subject/'), ('出版形式', '/directory/media/'),
                          ('出版语言', '/directory/language/')]:
        row[field] = '\n'.join(dict.fromkeys(a.get_text(' ', strip=True) for a in main.select('a[href]')
                                            if a['href'].startswith(prefix)))
    about = next((p for p in main.find_all('p') if p.get_text(' ', strip=True) == 'About'), None)
    if about:
        description = about.find_next_sibling('div')
        if description:
            row['详细介绍'] = description.get_text('\n', strip=True)
    websites, emails, phones, address = [], [], [], []
    contact_states, address_states = [], []
    # These boxes are rendered twice (desktop/mobile); dedupe values.
    for card in soup.select('.profile-card'):
        header = card.select_one('.profile-card-header')
        body = card.select_one('.profile-card-body')
        if not header or not body:
            continue
        title, value = header.get_text(' ', strip=True), body.get_text(' ', strip=True)
        if title == 'Websites & Contact':
            if 'Sign in' in value:
                contact_states.append('官网或联系方式需登录查看')
            if 'Premium only' in value:
                contact_states.append('投稿或版权部门信息限会员')
            for anchor in body.select('a[href]'):
                href = anchor['href'].strip()
                if href.lower().startswith('mailto:'):
                    emails.append(unquote(href[7:].split('?', 1)[0]))
                elif href.lower().startswith('tel:'):
                    phones.append(unquote(href[4:]))
                elif href.startswith(('https://', 'http://')) and urlsplit(href).hostname not in ('publishersglobal.com', 'www.publishersglobal.com'):
                    websites.append(href)
        elif title == 'Mailing Address':
            if 'Sign in' in value:
                address_states.append('完整地址需登录查看')
            else:
                address.append(value)
    row.update({'官网': '\n'.join(dict.fromkeys(websites)), '邮箱': explicit_emails(emails),
                '电话': '\n'.join(dict.fromkeys(phones)), '地址': '\n'.join(dict.fromkeys(address)),
                '联系方式状态': '；'.join(dict.fromkeys(contact_states)) or ('公开字段已读取' if websites or emails or phones else '公开页未提供'),
                '地址状态': '；'.join(dict.fromkeys(address_states)) or ('公开地址' if address else '公开页未提供'),
                '资料页状态': '已读取公开资料', '抓取时间': stamp})
    return row


class BrowserReader:
    def __init__(self, cache, timeout=35, delay=0.5, refresh=False):
        self.cache, self.timeout, self.delay, self.refresh = cache, timeout, delay, refresh
        cache.mkdir(parents=True, exist_ok=True)
        self.browser = self.page = self.playwright = None

    def start(self):
        if self.page:
            return
        from patchright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(channel='chrome', headless=True)
        self.page = self.browser.new_page()
        self.page.goto(COUNTRIES, wait_until='domcontentloaded', timeout=self.timeout * 1000)
        for _ in range(6):
            if 'moment' not in self.page.title().lower():
                break
            time.sleep(3)
        if 'moment' in self.page.title().lower():
            raise RuntimeError('浏览器验证尚未通过，已停止。请稍后重试；不会绕过登录或验证码。')

    def path(self, url):
        return self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')

    def read_batch(self, urls):
        results, missing = {}, []
        for url in urls:
            path = self.path(url)
            try:
                data = json.loads(path.read_text('utf-8'))
                if self.refresh or time.time() - data['timestamp'] > 7 * 86400:
                    missing.append(url)
                else:
                    results[url] = data
            except (OSError, ValueError, KeyError):
                missing.append(url)
        if missing:
            self.start()
            time.sleep(self.delay)
            data = self.page.evaluate('''async ({urls, timeout}) => Promise.all(urls.map(async url => {
                try {
                    const response = await fetch(url, {signal: AbortSignal.timeout(timeout)});
                    const text = await response.text();
                    const doc = new DOMParser().parseFromString(text, 'text/html');
                    const root = doc.querySelector('main');
                    const structured = [...doc.querySelectorAll('script[type="application/ld+json"]')].map(x=>x.outerHTML).join('');
                    return {url, status:response.status, finalUrl:response.url,
                        text:root ? root.outerHTML + structured : text,
                        retryAfter:response.headers.get('Retry-After')};
                } catch(error) { return {url,status:0,error:String(error)}; }
            }))''', {'urls': missing, 'timeout': self.timeout * 1000})
            for item in data:
                url = item['url']
                if item['status'] == 200 and '<h1' in item.get('text', ''):
                    item.update(timestamp=time.time(), time=datetime.now().isoformat(timespec='seconds'))
                    temp = self.path(url).with_suffix('.tmp')
                    temp.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
                    temp.replace(self.path(url))
                    results[url] = item
                else:
                    results[url] = item
        return results

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def write_csv(path, headers, rows):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["'" + str(v) if str(v).lstrip().startswith(('=', '+', '-', '@')) else v for v in row])
    temp.replace(path)


def save_results(folder, rows, coverage, errors):
    folder.mkdir(parents=True, exist_ok=True)
    data = sorted(rows.values(), key=lambda r: (r['国家或地区'], r['出版社名称'].casefold(), r['出版社编号']))
    write_csv(folder / '出版社信息.csv', FIELDS, [[r[k] for k in FIELDS] for r in data])
    coverage_headers = ['国家或地区', '国家目录列出数量', '列表页声明数量', '已抓取唯一出版社', '列表页状态', '目录来源']
    write_csv(folder / '国家覆盖检查.csv', coverage_headers, coverage)
    write_csv(folder / '异常记录.csv', ['阶段', '来源', '问题'], errors)
    temp = folder / 'publishers.tmp.json'
    temp.write_text(json.dumps({'fields': FIELDS, 'records': data, 'coverage': coverage,
                               'coverage_headers': coverage_headers, 'errors': errors}, ensure_ascii=False), encoding='utf-8')
    temp.replace(folder / 'publishers.json')


def run(args):
    folder = args.output.resolve()
    reader = BrowserReader(folder / 'cache', args.timeout, args.delay, args.refresh)
    rows, coverage, errors = {}, [], []
    blocked = 0

    def get_batch(urls, stage):
        nonlocal blocked
        results = reader.read_batch(urls)
        for url, item in list(results.items()):
            if item.get('status') != 200:
                # A brief server error or rate limit can be retried after a pause.
                for attempt in range(2):
                    if item.get('status') == 403:
                        break
                    delay = min(120, max(65 if item.get('status') == 429 else 5 * (attempt + 1), int(item.get('retryAfter') or 0)))
                    print(f'等待 {delay}s 后重试：{url}', flush=True)
                    time.sleep(delay)
                    item = reader.read_batch([url])[url]
                    if item.get('status') == 200:
                        results[url] = item
                        break
                if item.get('status') != 200:
                    errors.append([stage, url, f"HTTP {item.get('status')} {item.get('error', '')}"])
                    blocked += 1
                    if blocked >= 8:
                        raise RuntimeError('连续多次请求失败，已停止并保存进度，重跑会使用缓存')
            else:
                blocked = 0
        return results

    try:
        item = get_batch([COUNTRIES], '国家目录')[COUNTRIES]
        countries = parse_countries(item['text'])
        print(f'发现 {len(countries)} 个国家/地区，国家页合计 {sum(c["count"] for c in countries)} 条出版社。', flush=True)
        country_rows, totals, country_errors = {}, {}, {}
        jobs = [(c, c['url'], 1) for c in countries]
        offset = 0
        while offset < len(jobs):
            batch = jobs[offset:offset + args.workers]
            offset += len(batch)
            data = get_batch([job[1] for job in batch], '出版社列表')
            for country, url, number in batch:
                value = data[url]
                try:
                    if value.get('status') != 200:
                        raise ValueError(f'HTTP {value.get("status")}')
                    parsed, info = parse_listing(value['text'], country['country'], url, value['time'])
                    if info['page'] != number:
                        raise ValueError(f'请求第{number}页却返回第{info["page"]}页')
                    if number == 1:
                        totals[country['url']] = info['total']
                        jobs.extend((country, country['url'].rstrip('/') + f'/{p}', p) for p in range(2, info['pages'] + 1))
                    elif info['total'] != totals[country['url']]:
                        raise ValueError('目录在抓取期间数量变化，请刷新重试')
                    ids = country_rows.setdefault(country['url'], set())
                    if parsed and all(r['出版社编号'] in ids for r in parsed):
                        raise ValueError('分页返回重复公司集合')
                    for row in parsed:
                        ids.add(row['出版社编号'])
                        if row['出版社编号'] in rows and rows[row['出版社编号']]['国家或地区'] != row['国家或地区']:
                            raise ValueError('同一出版社编号出现在不同国家，需核对')
                        rows.setdefault(row['出版社编号'], row)
                except (ValueError, KeyError) as exc:
                    country_errors[country['url']] = True
                    errors.append(['出版社列表', url, str(exc)])
            coverage = [[c['country'], c['count'], totals.get(c['url'], ''), len(country_rows.get(c['url'], set())),
                         '完整' if (not country_errors.get(c['url']) and len(country_rows.get(c['url'], set())) == totals.get(c['url']) == c['count']) else '尚未完成或数量不符', c['url']]
                        for c in countries]
            if offset % 20 < args.workers or offset == len(jobs):
                save_results(folder, rows, coverage, errors)
                print(f'列表进度 {offset}/{len(jobs)} 页，已收集 {len(rows)} 家。', flush=True)
        save_results(folder, rows, coverage, errors)
        if not args.list_only:
            ids = list(rows)
            for offset in range(0, len(ids), args.workers):
                chunk = ids[offset:offset + args.workers]
                data = get_batch([rows[i]['资料来源'] for i in chunk], '出版社资料')
                for identifier in chunk:
                    row = rows[identifier]
                    item = data[row['资料来源']]
                    try:
                        if item.get('status') != 200:
                            raise ValueError(f'HTTP {item.get("status")}')
                        if PROFILE_PATH.fullmatch(urlsplit(item.get('finalUrl', row['资料来源'])).path).group(1) != identifier:
                            raise ValueError('资料页跳转到其他出版社或登录页')
                        rows[identifier] = parse_profile(item['text'], row, item['time'])
                    except (ValueError, KeyError, AttributeError) as exc:
                        row['资料页状态'] = '详情读取失败'
                        errors.append(['出版社资料', row['资料来源'], str(exc)])
                if offset % 100 < args.workers or offset + len(chunk) == len(ids):
                    save_results(folder, rows, coverage, errors)
                    print(f'资料进度 {offset + len(chunk)}/{len(ids)} 家。', flush=True)
    except KeyboardInterrupt:
        errors.append(['任务中断', COUNTRIES, '用户中断；再次运行会复用缓存'])
    except Exception as exc:
        errors.append(['任务异常', COUNTRIES, str(exc)])
        print(f'任务停止：{exc}', flush=True)
    finally:
        reader.close()
        save_results(folder, rows, coverage, errors)
        print(f'已保存 {len(rows)} 家出版社；异常 {len(errors)} 条；目录：{folder}', flush=True)
    return 0 if rows and not errors and all(c[4] == '完整' for c in coverage) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path.cwd() / 'output' / 'publishersglobal')
    parser.add_argument('--workers', type=int, choices=range(1, 7), default=2)
    parser.add_argument('--timeout', type=int, default=35)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--refresh', action='store_true', help='忽略7天页面缓存')
    parser.add_argument('--list-only', action='store_true', help='只抓取所有国家列表，不读取详情')
    args = parser.parse_args()
    if args.timeout <= 0 or not 0 <= args.delay <= 60:
        parser.error('timeout必须大于0，delay须介于0和60')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
