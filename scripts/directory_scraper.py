"""Site-specific company directories. Never extract organiser/footer contacts."""
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import phonenumbers
from bs4 import BeautifulSoup
from contact_core.extract_emails import deobfuscate_text
from contact_core.social_regexes import EMAIL_REGEX_GLOBAL

CBL = 'https://cbl.org.br/en/nossos-associados/'
BIENAL = 'https://www.bienaldolivrosp.com.br/pt-br/expositores.html'
EXTRA_HEADERS = ['目录类型', '公司编号', '展位', '国家', '城市或州', '目录来源', '电话原文', '数据时间']


def directory_kind(url):
    p = urlsplit(url if '://' in url else 'https://' + url)
    host = (p.hostname or '').removeprefix('www.')
    if host == 'bienaldolivrosp.com.br':
        return 'bienal'
    if host == 'cbl.org.br' and '/nossos-associados' in p.path:
        return 'cbl'
    return None


class DirectoryClient:
    """Cache only public responses, not request keys. Retriable read requests only."""
    def __init__(self, args):
        self.timeout = args.timeout
        self.delay = args.delay
        self.refresh = args.refresh_directories
        self.folder = args.output.resolve() / 'directory_cache'
        self.folder.mkdir(parents=True, exist_ok=True)

    def get(self, url, *, body=None, headers=None):
        key = hashlib.sha256((url + json.dumps(body, sort_keys=True)).encode()).hexdigest()
        path = self.folder / (key + '.json')
        if not self.refresh and path.exists():
            try:
                cached = json.loads(path.read_text('utf-8'))
                if time.time() - cached['timestamp'] < 86400:
                    return cached['text'], cached['time']
            except (ValueError, KeyError):
                pass
        from curl_cffi import requests as browser_requests
        last = None
        for attempt in range(3):
            time.sleep(self.delay + attempt)
            try:
                # This uses only the unauthenticated public page/search interface.
                response = browser_requests.request('POST' if body is not None else 'GET', url,
                    json=body, headers=headers, impersonate='chrome', timeout=self.timeout)
                response.raise_for_status()
                value = {'timestamp': time.time(), 'time': datetime.now().isoformat(timespec='seconds'),
                         'text': response.text}
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                temp.replace(path)
                return value['text'], value['time']
            except Exception as exc:
                last = exc
                if getattr(getattr(exc, 'response', None), 'status_code', 0) in (401, 403):
                    break
        raise RuntimeError(f'公开目录请求失败：{type(last).__name__}: {last}') from last


def base_record(raw, kind, name, source, stamp, identifier):
    from scrape_contacts import SUMMARY
    row = dict.fromkeys(SUMMARY, '')
    row.update({'输入网址': raw, '公司名称或网站标题': name, '目录类型': kind, '公司编号': identifier,
                '目录来源': source, '抓取时间': datetime.now().isoformat(timespec='seconds'),
                '数据时间': stamp, '成功页数': 1, '状态': '目录记录已提取'})
    return row


def normalize_phone(raw, region='BR'):
    normalized = []
    for value in re.split(r'\s*(?:/|;|\n)\s*', raw):
        if not value.strip():
            continue
        try:
            number = phonenumbers.parse(value, region)
            if phonenumbers.is_valid_number(number):
                value = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        if value not in normalized:
            normalized.append(value)
    return '\n'.join(normalized)


def explicit_emails(values):
    # Directory fields are authoritative as published; don't discard addresses
    # just because their local part is "mail", "name", "test", etc.
    found = []
    for value in values:
        for match in EMAIL_REGEX_GLOBAL.finditer(deobfuscate_text(value)):
            email = match.group().lower()
            if email not in found:
                found.append(email)
    return '\n'.join(found)


def company_details(row):
    result = []
    for kind, column in [('邮箱', '邮箱'), ('电话', '电话'), ('官网', '网站'), ('地址', '地址')]:
        for value in row[column].split('\n'):
            if value:
                result.append([row['输入网址'], row['公司名称或网站标题'], kind, value, row['目录来源']])
    for value in row['社交账号'].split('\n'):
        if value:
            result.append([row['输入网址'], row['公司名称或网站标题'], '社交账号', value, row['目录来源']])
    return result


def finish_record(row):
    missing = [key for key in ('邮箱', '电话', '网站') if not row[key]]
    if missing:
        row['备注'] = '目录未提供：' + '、'.join(missing)
    return row


def parse_cbl(text, source, raw, stamp):
    soup = BeautifulSoup(text, 'html.parser')
    cards = soup.select('.card-nossos-associados')
    if not cards:
        raise ValueError('未找到 CBL 公司卡片，可能返回拦截页或网页结构已变化')
    records = []
    for card in cards:
        name_tag = card.select_one('[data-id="headline-9-169"]') or card.find('h1')
        name = name_tag.get_text(' ', strip=True) if name_tag else ''
        if not name:
            raise ValueError('会员卡片缺少公司名称')
        address = '\n'.join(x.get_text(' ', strip=True) for x in card.select('.ct-text-block'))
        websites = [a['href'].strip() for a in card.select('a.ct-link[href]')
                    if a['href'].startswith(('http://', 'https://'))]
        # Card HTML IDs are reused on each page; do not use them as company IDs.
        identifier = 'cbl-' + hashlib.sha256((name.casefold() + '\n' + address + '\n' + '\n'.join(websites)).encode()).hexdigest()[:16]
        row = base_record(raw, 'CBL会员', name, source, stamp, identifier)
        row['地址'] = address
        row['城市或州'] = address.split('\n')[-1]
        row['国家'] = 'Brasil'
        row['网站'] = '\n'.join(dict.fromkeys(websites))
        row['邮箱'] = explicit_emails([a.get_text(' ', strip=True) + ' ' + unquote(a['href'][7:].split('?', 1)[0])
                                    for a in card.select('a[href^="mailto:"]')])
        # Phone matching is scoped to phone fields, not street numbers or ZIP codes.
        phones = [a.get_text(' ', strip=True) or unquote(a['href'][4:]) for a in card.select('a[href^="tel:"]')]
        row['电话原文'] = '\n'.join(dict.fromkeys(phones))
        row['电话'] = normalize_phone(row['电话原文'])
        records.append(finish_record(row))
    pages = {1}
    for anchor in soup.select('a.page-numbers[href]'):
        target = urlsplit(urljoin(source, anchor['href']))
        if target.hostname != urlsplit(source).hostname or target.path != urlsplit(source).path:
            continue
        number = parse_qs(target.query).get('sf_paged', ['1'])[0]
        if number.isdigit():
            pages.add(int(number))
    return records, max(pages)


def parse_bienal_settings(text):
    soup = BeautifulSoup(text, 'html.parser')
    container = soup.select_one('.exhibitor-directory')
    if container is None:
        raise ValueError('未找到公开展商目录组件；可能返回拦截页或页面结构已变化')
    for script in container.find_all('script'):
        match = re.search(r'JSON\.parse\(("(?:\\.|[^"\\])*")\)', script.string or '')
        if match:
            # Decode a JS string literal as data, never execute page JavaScript.
            literal = re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', match.group(1))
            settings = json.loads(json.loads(literal))
            if settings.get('packageName') == 'exhibitor-directory':
                return settings['props']
    raise ValueError('缺少展商目录公开配置')


def parse_bienal_hit(hit, raw, stamp, settings):
    context = settings['context']
    if hit.get('recordType') != 'exhibitor' or hit.get('eventEditionId') != context['eventEditionId']:
        raise ValueError('返回了其他展会或其他类型的数据，已停止以防混入')
    if hit.get('locale') != context['interfaceLocale'].lower():
        raise ValueError('展商记录语言与目录不符')
    identifier = hit['id']
    source = settings['navigation']['exhibitorPublicDetailsUrlFormat'].replace('{0}', identifier)
    row = base_record(raw, context.get('eventEditionName', 'Bienal展商'), hit.get('exhibitorName') or hit['companyName'].split('|')[0], source, stamp, identifier)
    row['展位'] = hit.get('standReference', '')
    row['国家'] = hit.get('countryName', '')
    row['网站'] = hit.get('website') or ''
    row['邮箱'] = explicit_emails([hit.get('email') or ''])
    row['电话原文'] = str(hit.get('phone') or '')
    row['电话'] = normalize_phone(row['电话原文'], 'BR' if row['国家'].casefold() in ('brasil', 'brazil') else None)
    # No regex over products/descriptions: those can mention unrelated contacts.
    return finish_record(row)


def scrape_directory(raw, args, checkpoint=None):
    kind = directory_kind(raw)
    client = DirectoryClient(args)
    records, logs, seen = [], [], set()
    fingerprints = set()
    source = CBL if kind == 'cbl' else BIENAL

    def accept(batch, page_url):
        fingerprint = tuple(sorted(row['公司编号'] for row in batch))
        if not fingerprint or fingerprint in fingerprints:
            raise ValueError('分页返回空记录或重复页，不能判定目录完整')
        fingerprints.add(fingerprint)
        for row in batch:
            if row['公司编号'] not in seen:
                seen.add(row['公司编号'])
                records.append(row)
        logs.append([raw, page_url, '成功', f'本页 {len(batch)} 条，累计 {len(records)} 家'])
        print(f'  目录累计 {len(records)} 家：{page_url}', flush=True)
        if checkpoint:
            checkpoint(records, [d for row in records for d in company_details(row)], logs)

    try:
        text, stamp = client.get(source)
        if kind == 'cbl':
            batch, pages = parse_cbl(text, source, raw, stamp)
            accept(batch, source)
            total_expected = None

            def load(number):
                target = source + f'?sf_paged={number}'
                text, stamp = client.get(target)
                batch, discovered_pages = parse_cbl(text, target, raw, stamp)
                if discovered_pages > pages:
                    raise ValueError('抓取期间会员目录分页增加，请刷新后重试')
                return batch, target

            numbers = range(2, min(pages, args.directory_pages) + 1)
        else:
            settings = parse_bienal_settings(text)
            config, context = settings['algoliaConfig'], settings['context']
            # Same public index, locale and event filter used by the site's JS.
            endpoint = f"https://{config['appId'].lower()}-dsn.algolia.net/1/indexes/{context['eventId']}-index/query"
            headers = {'X-Algolia-Application-Id': config['appId'], 'X-Algolia-API-Key': config['apiKey']}

            def query(number):
                body = {'filters': f"recordType:exhibitor AND locale:{context['interfaceLocale'].lower()} AND eventEditionId:{context['eventEditionId']}",
                        'hitsPerPage': 100, 'page': number}
                value, stamp = client.get(endpoint, body=body, headers=headers)
                data = json.loads(value)
                if data.get('page') != number or 'hits' not in data:
                    raise ValueError('展商接口分页结构异常')
                return data, stamp

            data, stamp = query(0)
            pages, total_expected = data['nbPages'], data['nbHits']
            accept([parse_bienal_hit(h, raw, stamp, settings) for h in data['hits']], source + '?page=1')

            def load(number):
                data, stamp = query(number - 1)
                if data['nbHits'] != total_expected:
                    raise ValueError('抓取期间目录总数变化，请刷新后重试')
                return [parse_bienal_hit(h, raw, stamp, settings) for h in data['hits']], source + f'?page={number}'

            numbers = range(2, min(pages, args.directory_pages) + 1)
        errors = 0
        pool = ThreadPoolExecutor(max_workers=args.directory_workers)
        try:
            pending = {pool.submit(load, number): number for number in numbers}
            for future in as_completed(pending):
                try:
                    batch, target = future.result()
                    accept(batch, target)
                except Exception as exc:
                    errors += 1
                    logs.append([raw, f'{source}?page={pending[future]}', '失败', str(exc)[:500]])
                    print(f'  目录第 {pending[future]} 页失败：{exc}', flush=True)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        complete = not errors and pages <= args.directory_pages and (total_expected is None or len(records) == total_expected)
        note = f'成功 {len(fingerprints)}/{pages} 页；公司 {len(records)}' + (f'/{total_expected}' if total_expected is not None else '')
        logs.append([raw, source, '目录完整' if complete else '目录不完整', note])
        if not complete:
            for row in records:
                row['备注'] = '；'.join(filter(None, [row['备注'], '本次目录抓取不完整，见抓取日志']))
        print(f'  {logs[-1][2]}：{note}', flush=True)
    except Exception as exc:
        logs.append([raw, source, '目录失败', str(exc)[:500]])
        print(f'  目录失败：{exc}', flush=True)
    records.sort(key=lambda r: (r['公司名称或网站标题'].casefold(), r['公司编号']))
    return records, [d for row in records for d in company_details(row)], logs
