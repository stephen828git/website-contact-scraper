import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from directory_scraper import (BIENAL, CBL, directory_kind, parse_cbl,
    parse_bienal_hit, parse_bienal_settings, scrape_directory)


def card(name, mail, phone, address='Rua 123, 456'):
    return f'''<div class="card-nossos-associados"><h1>{name}</h1>
    <div class="ct-text-block">{address}</div>
    <a class="ct-link" href="https://shared-publisher.com">Site</a>
    <a href="mailto:{mail}">{mail}</a><a href="tel:{phone}">{phone}</a></div>'''


class DirectoryTests(unittest.TestCase):
    def test_company_isolation_and_explicit_email(self):
        text = card('Editora A', 'mail@publisher-a.com', '(11) 3333-4444')
        text += card('Editora B', 'sales@publisher-b.com', '(21) 2222-3333')
        text += '<footer>organizer@cbl.org.br +55 11 99999-1111</footer>'
        text += '<a class="page-numbers" href="?sf_paged=79">79</a>'
        records, pages = parse_cbl(text, CBL, CBL, 'now')
        self.assertEqual(pages, 79)
        self.assertEqual(records[0]['邮箱'], 'mail@publisher-a.com')
        self.assertEqual(records[1]['邮箱'], 'sales@publisher-b.com')
        self.assertNotEqual(records[0]['公司编号'], records[1]['公司编号'])
        self.assertEqual(records[0]['电话'], '+551133334444')
        self.assertNotIn('456', records[0]['电话'])
        self.assertNotIn('organizer', str(records))

    def test_bienal_identity_and_only_own_fields(self):
        props = {'context': {'eventEditionId': 'eve-one', 'interfaceLocale': 'pt-BR', 'eventEditionName': 'Bienal 2026'},
                 'navigation': {'exhibitorPublicDetailsUrlFormat': BIENAL + '/{0}'}}
        hit = {'recordType': 'exhibitor', 'id': 'exh-1', 'companyName': 'RAW|internal|ID',
               'exhibitorName': 'Public company', 'eventEditionId': 'eve-one', 'locale': 'pt-br',
               'email': 'sales@publisher.com', 'phone': '1133334444', 'standReference': 'A01',
               'products': [{'description': 'unrelated@other.com'}]}
        row = parse_bienal_hit(hit, BIENAL, 'now', props)
        self.assertEqual(row['公司名称或网站标题'], 'Public company')
        self.assertEqual(row['邮箱'], 'sales@publisher.com')
        self.assertEqual(row['展位'], 'A01')
        hit['eventEditionId'] = 'eve-other'
        with self.assertRaises(ValueError):
            parse_bienal_hit(hit, BIENAL, 'now', props)

    def test_safe_settings_decoding(self):
        expected = {'context': {'name': 'São Paulo'}}
        encoded = json.dumps(json.dumps({'packageName': 'exhibitor-directory', 'props': expected}))
        encoded = encoded.replace('\\"', '\\x22')
        text = '<div class="exhibitor-directory"><script>var x=JSON.parse(' + encoded + ');</script></div>'
        self.assertEqual(parse_bienal_settings(text), expected)
        with self.assertRaises(ValueError):
            parse_bienal_settings('<h1>Access denied</h1>')

    def test_repeat_page_not_reported_complete(self):
        text = card('A', 'a@publisher.com', '(11) 3333-4444')
        text += '<a class="page-numbers" href="?sf_paged=2">2</a>'
        with tempfile.TemporaryDirectory() as folder:
            args = argparse.Namespace(timeout=2, delay=0, refresh_directories=False,
                                      output=Path(folder), directory_pages=200, directory_workers=1)
            with patch('directory_scraper.DirectoryClient.get', return_value=(text, 'now')):
                rows, _, logs = scrape_directory(CBL, args)
        self.assertEqual(len(rows), 1)
        self.assertEqual(logs[-1][2], '目录不完整')

    def test_detection_and_no_card_failure(self):
        self.assertEqual(directory_kind('https://www.bienaldolivrosp.com.br/'), 'bienal')
        self.assertEqual(directory_kind(CBL), 'cbl')
        self.assertIsNone(directory_kind('https://other.com/'))
        with self.assertRaises(ValueError):
            parse_cbl('<footer>email@cbl.org.br</footer>', CBL, CBL, 'now')


if __name__ == '__main__':
    unittest.main()
