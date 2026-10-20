import tempfile
import json
from argparse import Namespace
import unittest
from pathlib import Path
from unittest.mock import patch
from contact_core.html_text import build_page
from publishersglobal_contacts import owned_email, crawl_site, norm, enrich
from publishersglobal_scraper import FIELDS


class PublicContactTests(unittest.TestCase):
    def test_external_vendor_email_requires_explicit_allowlist(self):
        self.assertTrue(owned_email('sales@press.co.uk','https://www.press.co.uk'))
        self.assertFalse(owned_email('web@agency.co.uk','https://press.co.uk'))
        self.assertFalse(owned_email('fake@press.co.uk.evil.com','https://press.co.uk'))
        self.assertTrue(owned_email('sales@group.org','https://press.co.uk',['group.org']))

    def test_homepage_author_address_is_not_company_contact(self):
        home=build_page('https://press.com/', '<main>Book author author@press.com</main><footer>sales@press.com</footer><a href="/contact">Contact</a>')
        contact=build_page('https://press.com/contact','<main>rights@press.com</main>')
        with tempfile.TemporaryDirectory() as d, patch('publishersglobal_contacts.fetch',side_effect=[home,contact]), patch('publishersglobal_contacts.time.sleep'):
            result=crawl_site({'url':'https://press.com/','country':'United Kingdom'},Path(d))
        self.assertEqual({v[1] for v in result['hits']},{'sales@press.com','rights@press.com'})

    def test_redirect_to_different_company_is_rejected(self):
        page=build_page('https://another.com/','<footer>sales@another.com</footer>')
        with tempfile.TemporaryDirectory() as d, patch('publishersglobal_contacts.fetch',return_value=page):
            result=crawl_site({'url':'https://press.com/','country':'United Kingdom'},Path(d))
        self.assertEqual(result['hits'],[])
        self.assertIn('跨域',result['logs'][0][1])

    def test_normalization_keeps_distinct_names_distinct(self):
        self.assertEqual(norm('Edições Loyola'),norm('Edicoes Loyola'))
        self.assertNotEqual(norm('Editora Contexto'),norm('Contexto'))

    def test_enrichment_keeps_unknown_rows_and_quarantines_wrong_contacts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            records=[]
            for identifier,name in [('1','press.com'),('2','Unknown Publisher')]:
                r=dict.fromkeys(FIELDS,'')
                r.update({'出版社编号':identifier,'出版社名称':name,'国家或地区':'United Kingdom','资料来源':'https://directory.test/'+identifier})
                records.append(r)
            source=root/'input.json'
            source.write_text(json.dumps({'records':records,'fields':FIELDS,'coverage':[],'coverage_headers':[],'errors':[]}),encoding='utf-8')
            result={'hits':[['邮箱','sales@press.com','https://press.com/contact'],['邮箱','web@agency.com','https://press.com/contact'],['电话','+497156163','https://press.com/contact'],['电话','+4971561630','https://press.com/contact']], 'logs':[['https://press.com/contact','成功']],'time':'2026-09-16'}
            args=Namespace(input=source,previous=root/'none',seeds=root/'none',exclusions=root/'none',output=root/'out',workers=1,refresh=False)
            with patch('publishersglobal_contacts.crawl_site',return_value=result):
                enrich(args)
            data=json.loads((args.output/'publishers_enriched.json').read_text('utf-8'))
            self.assertEqual(len(data['records']),2)
            self.assertEqual(data['records'][0]['邮箱'],'sales@press.com')
            self.assertEqual(data['records'][0]['电话'],'+4971561630')
            self.assertEqual(data['records'][1]['邮箱'],'')
            self.assertEqual(len(data['review_contacts']),2)


if __name__=='__main__': unittest.main()
