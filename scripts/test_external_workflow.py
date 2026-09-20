import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from external_guard import Guard,key,validate_review,validate_personal_answers,ledger_records,hostname_is
from polite_http import PoliteJson,retry_seconds

POLICY=json.loads((Path(__file__).parent/'external_policy.example.json').read_text())
NOW=dt.datetime(2026,9,12,20,tzinfo=dt.timezone.utc).timestamp()

class ExternalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.ledger=self.root/'log.md';self.ledger.write_text('')
    def guard(self,now=NOW,**overrides):
        g=Guard(self.root/'state.db',self.ledger,POLICY|overrides,now)
        self.addCleanup(g.db.close);return g
    def test_linkedin_disabled_and_embed_dedup(self):
        self.assertEqual(key('https://boards.greenhouse.io/embed/job_app?for=varda&token=123'),key('https://job-boards.greenhouse.io/varda/jobs/123?gh_src=x'))
        self.assertIn('LinkedIn disabled',self.guard().check('https://www.linkedin.com/jobs/view/123','X','b'))
    def test_provider_domains_reject_lookalikes_and_query_text(self):
        self.assertTrue(hostname_is('https://apply.workable.com/example', 'workable.com'))
        for url in ['https://fakeworkable.com/', 'https://workable.com.evil.example/', 'https://evil.example/?site=workable.com']:
            self.assertFalse(hostname_is(url, 'workable.com'))
        self.assertFalse(key('https://fakegreenhouse.io/acme/jobs/123').startswith('gh:'))
    def test_legacy_count_excludes_unconfirmed_and_linkedin(self):
        self.ledger.write_text('2026-09-12 | A | Role | External | applied - CONFIRMED | pay | https://a.test/jobs/1\n'
          '| 2026-09-12 | B | Role | External | applied - NOT-CONFIRMED | pay | https://b.test/jobs/2 |\n'
          '2026-09-12 | C | Role | LinkedIn Easy Apply | applied - CONFIRMED | pay | https://linkedin.com/jobs/view/3\n')
        self.assertEqual(self.guard().status()['confirmed'],1)
    def test_reservation_survives_restart_and_prevents_duplicate(self):
        g=self.guard();self.assertEqual(g.reserve('https://a.test/jobs/1','A','Role','b'),'GO')
        g2=self.guard(NOW+500)
        self.assertIn('unresolved',g2.reserve('https://a.test/jobs/1','A','Role','b'))
        self.assertEqual(g2.status()['confirmed'],0)
        self.assertEqual(g2.status()['pending'],1)
    def test_existing_unconfirmed_attempt_is_not_retried(self):
        self.ledger.write_text('2026-09-12 | Miter | Support | External | filled-not-submitted:validation (two submit attempts; no confirmation) | pay | https://jobs.ashbyhq.com/miter/abc\n')
        self.assertIn('unresolved',self.guard().check('https://jobs.ashbyhq.com/miter/abc/','Miter','b'))
    def test_quota_counts_pending_but_never_calls_it_confirmed(self):
        g=self.guard(daily_target=1);g.reserve('https://a.test/jobs/1','A','Role','b')
        self.assertIn('target reached',g.check('https://b.test/jobs/2','B','b'))
        with self.assertRaises(ValueError):g.finish('https://a.test/jobs/1',True,'success','')
        proof=self.root/'success.txt';proof.write_text('Application received')
        g.finish('https://a.test/jobs/1',True,'https://a.test/confirmation',str(proof))
        self.assertEqual(g.status()['confirmed'],1)
    def test_spacing_and_cooldown_persist(self):
        g=self.guard(batch_target=2);g.reserve('https://a.test/jobs/1','A','Role','b')
        self.assertIn('WAIT:',g.check('https://b.test/jobs/2','B','b'))
        g.block('https://b.test/jobs/2',7200,'429')
        self.assertIn('cooldown',self.guard(NOW+500,batch_target=2).check('https://b.test/jobs/2','B','b'))
    def test_batch_limit_and_midnight(self):
        g=self.guard(batch_target=1);u='https://a.test/jobs/1';g.reserve(u,'A','R','b')
        proof=self.root/'proof';proof.write_text('confirmed');g.finish(u,True,'confirmation',str(proof))
        self.assertIn('batch target',g.check('https://b.test/jobs/2','B','b'))
        self.assertEqual(self.guard(NOW+86400).status()['confirmed'],0)
    def test_schedule_and_exact_worksite_required(self):
        r={'fit_reviewed':True,'schedule_notes':'Weekday business hours','schedule_conflict':False,'workplace':'remote','ca_eligible':True}
        self.assertEqual(validate_review(r,POLICY),'')
        self.assertTrue(validate_review(r|{'schedule_conflict':True},POLICY))
        local=r|{'workplace':'onsite','distance_miles':14,'distance_evidence':'verified worksite distance'}
        self.assertEqual(validate_review(local,POLICY),'')
        self.assertTrue(validate_review(local|{'distance_miles':16},POLICY))
        self.assertTrue(validate_review(local|{'distance_evidence':''},POLICY))
    def test_guessed_personal_answers_cannot_pass_with_a_filled_config(self):
        cfg={'selects':{'q':'Yes'},'unmapped_required':[{'name':'q','label':'Can you perform all essential functions?'}]}
        self.assertIn('User answer needed',validate_personal_answers(cfg,POLICY))
        cfg['unmapped_required'][0]['label']='Are you subject to employment agreements or post-employment restrictions?'
        self.assertIn('User answer needed',validate_personal_answers(cfg,POLICY))
    def test_cache_reuses_public_response(self):
        calls=[]
        def fetch(req,**kw):calls.append(req.full_url);return io.BytesIO(b'{"jobs":[]}')
        client=PoliteJson(self.root/'cache',opener=fetch,clock=lambda:NOW)
        self.assertEqual(client.get('https://a.test/jobs'),{'jobs':[]})
        second=PoliteJson(self.root/'cache',opener=fetch,clock=lambda:NOW+30)
        second.get('https://a.test/jobs')
        self.assertEqual(len(calls),1)
    def test_retry_after_is_honored_across_restarts(self):
        calls=[]
        def fetch(req,**kw):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url,429,'rate limit',{'Retry-After':'7200'},None)
        client=PoliteJson(self.root/'cache',opener=fetch,clock=lambda:NOW)
        with self.assertRaises(urllib.error.HTTPError):client.get('https://a.test/jobs')
        second=PoliteJson(self.root/'cache',opener=fetch,clock=lambda:NOW+4000)
        with self.assertRaises(RuntimeError):second.get('https://a.test/other')
        self.assertEqual(len(calls),1)
        self.assertEqual(retry_seconds('Sat, 12 Sep 2026 22:00:00 GMT',NOW),7200)

if __name__=='__main__':unittest.main()
