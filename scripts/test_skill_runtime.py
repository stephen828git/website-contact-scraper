"""Exercise the installed-style CLI from an unrelated task directory, offline."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from publishersglobal_scraper import FIELDS
from test_scraper import Handler


SCRIPTS = Path(__file__).resolve().parent


def run_cli(script, cwd, *args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', NO_PROXY='127.0.0.1,localhost',
               no_proxy='127.0.0.1,localhost')
    return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(SCRIPTS / script), *args],
                          cwd=cwd, env=env, capture_output=True, text=True,
                          encoding='utf-8', timeout=30)


class SkillRuntimeTests(unittest.TestCase):
    def test_bom_url_list_and_default_output_in_task_directory(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory(prefix='联系方式 skill ') as temp:
                task = Path(temp)
                urls = task / '网址 清单.txt'
                urls.write_text(f'# local fixture\nhttp://127.0.0.1:{server.server_port}\n',
                                encoding='utf-8-sig')
                result = run_cli('scrape_contacts.py', task, '-i', str(urls), '--max-pages',
                                 '1', '--delay', '0', '--csv-only')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                reports = list((task / 'output' / 'website-contacts').glob('*/公司汇总.csv'))
                self.assertEqual(len(reports), 1)
                with reports[0].open(encoding='utf-8-sig', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['公司名称或网站标题'], '测试公司')
                self.assertIn('sales@realbusiness.cn', rows[0]['邮箱'])
                self.assertIn('页面上限', rows[0]['备注'])
        finally:
            server.shutdown()
            server.server_close()

    def test_enrichment_without_old_project_inputs_preserves_unknown_companies(self):
        with tempfile.TemporaryDirectory(prefix='联系人 enrichment ') as temp:
            task = Path(temp)
            row = dict.fromkeys(FIELDS, '')
            row.update({'出版社编号': '99', '出版社名称': 'Unverified Publisher',
                        '国家或地区': 'United Kingdom',
                        '资料来源': 'https://directory.invalid/99'})
            roster = task / '名录.json'
            roster.write_text(json.dumps({'fields': FIELDS, 'records': [row], 'coverage': [],
                                         'coverage_headers': [], 'errors': []}), encoding='utf-8-sig')
            result = run_cli('publishersglobal_contacts.py', task, '--input', str(roster))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = task / 'output' / 'publishersglobal_enriched' / 'publishers_enriched.json'
            data = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(len(data['records']), 1)
            self.assertEqual(data['records'][0]['出版社编号'], '99')
            self.assertEqual(data['records'][0]['邮箱'], '')
            self.assertEqual(data['contact_details'], [])
            self.assertEqual(data['contact_logs'], [])
            self.assertEqual(json.loads(roster.read_text('utf-8-sig'))['records'], [row])

    def test_missing_explicit_input_is_reported_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_cli('publishersglobal_contacts.py', temp, '--input', 'missing.json')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('文件不存在', result.stderr)
            self.assertFalse((Path(temp) / 'output').exists())


if __name__ == '__main__':
    unittest.main()
