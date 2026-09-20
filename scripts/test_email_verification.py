import datetime as dt
import json
import unittest
import test_external_workflow as fixtures
from email_verification import matching_code,mark_used

NOW=fixtures.NOW

class EmailTests(unittest.TestCase):
    setUp=fixtures.ExternalTests.setUp
    guard=fixtures.ExternalTests.guard
    def code_file(self, **changes):
        item={'sender':'no-reply@us.greenhouse-mail.io','subject':'Security code for your application to Testco',
              'received_utc':dt.datetime.fromtimestamp(NOW,dt.timezone.utc).isoformat(),'code':'12AB56CD',
              'gmail_message_id':'synthetic-message'} | changes
        p=self.root/'codes.json';p.write_text(json.dumps({'codes':[item]}));return p
    def test_only_matching_recent_application_code(self):
        p=self.code_file()
        self.assertIsNotNone(matching_code(p,'Testco',NOW-10,NOW))
        self.assertIsNone(matching_code(p,'Another',NOW-10,NOW))
        self.assertIsNone(matching_code(p,'Testco',NOW+20,NOW+30))
        self.assertIsNone(matching_code(p,'Testco',0,NOW+3601))
        self.assertIsNone(matching_code(self.code_file(sender='untrusted@example.com'),'Testco',0,NOW))
    def test_used_code_cleared_and_never_reused(self):
        p=self.code_file();item=matching_code(p,'Testco',0,NOW);mark_used(p,item)
        self.assertNotIn('12AB56CD',p.read_text())
        self.assertIsNone(matching_code(p,'Testco',0,NOW))
    def test_continuation_is_once_and_does_not_double_count(self):
        g=self.guard();u='https://a.test/jobs/1';p=self.code_file()
        self.assertIn('STOP',g.resume_email_verification(u,'Testco',p))
        g.reserve(u,'Testco','Role','b');g.finish(u,False,'Awaiting code')
        self.assertEqual(g.resume_email_verification(u,'Testco',p),'GO')
        self.assertEqual(g.status()['confirmed'],0)
        g.finish(u,False,'Still unresolved')
        self.assertIn('already attempted',g.resume_email_verification(u,'Testco',p))
    def test_no_continuation_of_confirmed_application(self):
        g=self.guard();u='https://a.test/jobs/1';p=self.code_file();proof=self.root/'proof';proof.write_text('Confirmed')
        g.reserve(u,'Testco','Role','b');g.finish(u,True,'confirmation',str(proof))
        self.assertIn('STOP',g.resume_email_verification(u,'Testco',p))

if __name__=='__main__':unittest.main()
