import json
import unittest
from publishersglobal_scraper import parse_countries, parse_listing, parse_profile


class PublishersGlobalTests(unittest.TestCase):
    def test_country_scope(self):
        text = '''<main><h1>Countries</h1>
        <a class="nav-vertical-link-flex" href="/directory/brazil/publishers-in-brazil"><span>Brazil</span><span class="count-badge">1,234 publishers</span></a>
        <a class="nav-vertical-link-flex" href="/directory/brazil/service-providers"><span>Brazil services</span><span class="count-badge">99 providers</span></a></main>'''
        countries = parse_countries(text)
        self.assertEqual(len(countries), 1)
        self.assertEqual(countries[0]['count'], 1234)

    def test_listing_excludes_suppliers_and_uses_id(self):
        text = '<main><h1>Publishers</h1><p>1–20 of 63 publishers · Page 1 of 4</p>'
        for path in ('publisher-profile/123', 'service-provider-profile/456'):
            text += f'<div class="entity-card"><a class="entity-card-name" href="/directory/{path}">Company</a><div class="entity-card-meta">City, Brazil</div><p class="entity-card-brief">Books</p></div>'
        text += '</main>'
        rows, metadata = parse_listing(text, 'Brazil', 'https://www.publishersglobal.com/directory/brazil/publishers-in-brazil', 'now')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['出版社编号'], '123')
        self.assertEqual(metadata, {'pages': 4, 'page': 1, 'total': 63})

    def test_locked_fields_are_not_guessed(self):
        row = {'出版社名称': 'Company'}
        text = '''<main><main><div><h1>Company</h1><p>City</p></div>
        <p>About</p><div><p>Contact fake@mentioned.com in this description.</p></div>
        <a href="/directory/subject/fiction-publishers">Fiction</a></main>
        <div class="profile-card"><div class="profile-card-header">Websites &amp; Contact</div><div class="profile-card-body">Website <a href="/users/sign_in">Sign in</a> Submissions Premium only</div></div>
        <div class="profile-card"><div class="profile-card-header">Mailing Address</div><div class="profile-card-body">City <a href="/users/sign_in">Sign in to view full address</a></div></div></main>
        <footer><a href="mailto:admin@publishersglobal.com">Admin</a></footer>'''
        parsed = parse_profile(text, row, 'now')
        self.assertEqual(parsed['邮箱'], '')
        self.assertEqual(parsed['官网'], '')
        self.assertEqual(parsed['地址'], '')
        self.assertIn('需登录', parsed['联系方式状态'])
        self.assertEqual(parsed['出版类别'], 'Fiction')

    def test_public_contact_fields(self):
        text = '''<main><h1>Company</h1><div class="profile-card"><div class="profile-card-header">Websites &amp; Contact</div><div class="profile-card-body"><a href="https://publisher.test">Website</a><a href="mailto:mail%40publisher.test">Email</a><a href="tel:+12345">Phone</a></div></div></main>'''
        parsed = parse_profile(text, {}, 'now')
        self.assertEqual(parsed['官网'], 'https://publisher.test')
        self.assertEqual(parsed['邮箱'], 'mail@publisher.test')
        self.assertEqual(parsed['电话'], '+12345')

    def test_challenge_is_not_empty_success(self):
        with self.assertRaises(ValueError):
            parse_listing('<title>Just a moment</title>', 'Brazil', 'https://example.test', 'now')


if __name__ == '__main__':
    unittest.main()
