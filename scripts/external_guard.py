"""Persistent external-application accounting. No networking or form submission."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit, parse_qs
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
APPS = Path(os.environ.get('JOBHUNT_APPLICATIONS', str(HERE.parent / 'applications')))
POLICY = Path(os.environ.get('JOBHUNT_POLICY', str(HERE / 'external_policy.json')))


def key(url):
    p = urlsplit(url.strip())
    host = (p.hostname or '').lower()
    q = parse_qs(p.query)
    if 'greenhouse.io' in host:
        if q.get('for') and q.get('token'):
            return 'gh:' + q['for'][0].lower() + ':' + q['token'][0]
        m = re.search(r'/([^/]+)/jobs/(\d+)', p.path)
        if m:
            return 'gh:' + m[1].lower() + ':' + m[2]
    if host == 'jobs.ashbyhq.com':
        return 'ashby:' + p.path.strip('/').lower()
    for param in ('gh_jid', 'jobId', 'job_id', 'requisitionId'):
        if q.get(param):
            return host + ':' + param.lower() + ':' + q[param][0]
    return host + p.path.rstrip('/')


def linkedin(url):
    host = (urlsplit(url).hostname or '').lower()
    return host == 'linkedin.com' or host.endswith('.linkedin.com')


def ledger_records(path):
    if not Path(path).exists():
        return []
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        c = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(c) < 7 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', c[0]):
            continue
        status = c[4].lower()
        if not re.search(r'\b(applied|submitted)\b', status) or 'confirmed' not in status:
            continue
        if any(w in status for w in ('not-confirmed','unconfirmed','not-submitted','uncertain')):
            continue
        match = re.search(r'https?://[^\s|)>]+', c[6])
        if not match:
            continue
        url = match[0]
        if linkedin(url) or ('linkedin' in c[3].lower() and 'external' not in c[3].lower()):
            continue
        rows.append({'day':c[0], 'company':c[1].casefold(), 'key':key(url)})
    return rows


def unresolved_keys(path):
    if not Path(path).exists():return set()
    result=set()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        c=[x.strip() for x in line.strip().strip('|').split('|')]
        if len(c)<7 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',c[0]):continue
        s=c[4].lower()
        if s=='attempting' or 'unconfirmed' in s or 'no confirmation' in s or ('filled-not-submitted' in s and 'submit attempts' in s):
            m=re.search(r'https?://[^\s|)>]+',c[6])
            if m:result.add(key(m[0]))
    return result


class Guard:
    def __init__(self, db=None, ledger=None, policy=None, now=None):
        self.policy = policy or json.loads(POLICY.read_text())
        self.fixed_now = now
        self.now = time.time() if now is None else now
        self.day = dt.datetime.fromtimestamp(self.now, ZoneInfo(self.policy['timezone'])).date().isoformat()
        self.ledger = Path(ledger or APPS / '_run_log.md')
        path = Path(db or APPS / '_external_applications.sqlite3')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS attempts (
            job_key TEXT PRIMARY KEY, url TEXT, company TEXT, title TEXT,
            batch TEXT, day TEXT, state TEXT, started REAL, confirmed REAL,
            evidence TEXT, proof TEXT);
            CREATE TABLE IF NOT EXISTS blocks (host TEXT PRIMARY KEY, until REAL, reason TEXT);''')

    def refresh(self):
        self.now = time.time() if self.fixed_now is None else self.fixed_now
        self.day = dt.datetime.fromtimestamp(self.now, ZoneInfo(self.policy['timezone'])).date().isoformat()

    def status(self, batch=None):
        self.refresh()
        legacy = ledger_records(self.ledger)
        confirmed = {r['key'] for r in legacy if r['day'] == self.day}
        confirmed.update(r[0] for r in self.db.execute("SELECT job_key FROM attempts WHERE state='confirmed' AND day=?", (self.day,)))
        pending = self.db.execute("SELECT count(*) FROM attempts WHERE state='pending' AND day=?", (self.day,)).fetchone()[0]
        batch_count = self.db.execute("SELECT count(*) FROM attempts WHERE state='confirmed' AND batch=? AND day=?", (batch,self.day)).fetchone()[0] if batch else 0
        batch_pending = self.db.execute("SELECT count(*) FROM attempts WHERE state='pending' AND batch=? AND day=?", (batch,self.day)).fetchone()[0] if batch else 0
        return {'date':self.day, 'confirmed':len(confirmed), 'pending':pending,
                'target':self.policy['daily_target'], 'remaining':max(0,self.policy['daily_target']-len(confirmed)),
                'batch_confirmed':batch_count, 'batch_pending':batch_pending, 'batch_target':self.policy['batch_target']}

    def check(self, url, company, batch):
        self.refresh()
        if linkedin(url):
            return 'STOP: LinkedIn disabled by user'
        if urlsplit(url).scheme != 'https' or not company.strip():
            return 'STOP: valid HTTPS employer URL and company required'
        k = key(url)
        legacy = ledger_records(self.ledger)
        if any(r['key'] == k for r in legacy) or k in unresolved_keys(self.ledger) or self.db.execute('SELECT 1 FROM attempts WHERE job_key=?', (k,)).fetchone():
            return 'STOP: existing application or unresolved attempt; inspect evidence before any manual retry'
        status = self.status(batch)
        if status['confirmed'] + status['pending'] >= status['target']:
            return 'STOP: daily target reached or reserved'
        if status['batch_confirmed'] + status['batch_pending'] >= status['batch_target']:
            return 'STOP: batch target reached'
        host = urlsplit(url).hostname
        block = self.db.execute('SELECT until,reason FROM blocks WHERE host=?',(host,)).fetchone()
        if block and block['until'] > self.now:
            return 'STOP: source cooldown: ' + block['reason']
        company = company.casefold()
        daily = {r['key'] for r in legacy if r['day']==self.day and r['company']==company}
        daily.update(r[0] for r in self.db.execute("SELECT job_key FROM attempts WHERE company=? AND day=? AND state IN ('pending','confirmed')",(company,self.day)))
        if len(daily) >= self.policy['per_employer_daily_limit']:
            return 'STOP: employer daily limit'
        last = self.db.execute('SELECT max(started) FROM attempts').fetchone()[0]
        wait = int(last + self.policy['min_submit_interval_seconds'] - self.now + 0.999) if last else 0
        if wait > 0:
            return f'WAIT:{wait}: submission spacing'
        return 'GO'

    def reserve(self, url, company, title, batch):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            answer = self.check(url, company, batch)
            if answer == 'GO':
                self.db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (key(url),url,company.casefold(),title,batch,self.day,'pending',self.now,None,None,None))
            self.db.execute('COMMIT')
            return answer
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def finish(self, url, confirmed=False, evidence='', proof=''):
        self.refresh()
        if confirmed and (not evidence or not Path(proof).is_file() or Path(proof).stat().st_size == 0):
            raise ValueError('Confirmed applications require observed confirmation URL/text and a saved evidence file')
        changed = self.db.execute("UPDATE attempts SET state=?,confirmed=?,evidence=?,proof=? WHERE job_key=? AND state='pending'",
            ('confirmed' if confirmed else 'unconfirmed',self.now if confirmed else None,evidence,proof,key(url))).rowcount
        if changed != 1:
            raise ValueError('Exactly one pending reservation is required')

    def resume_email_verification(self, url, company, code_file):
        from email_verification import matching_code
        self.refresh()
        item = matching_code(code_file, company, now=self.now)
        if not item or not item.get('gmail_message_id'):
            return 'STOP: matching recent application email code required'
        self.db.execute('CREATE TABLE IF NOT EXISTS email_resumes (job_key TEXT PRIMARY KEY, message_id TEXT, started REAL)')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT * FROM attempts WHERE job_key=?',(key(url),)).fetchone()
            if not row or row['state'] != 'unconfirmed' or row['company'] != company.casefold():
                answer = 'STOP: exactly one matching unconfirmed attempt required'
            elif self.db.execute('SELECT 1 FROM email_resumes WHERE job_key=?',(key(url),)).fetchone():
                answer = 'STOP: email verification continuation already attempted'
            elif self.status()['confirmed'] + self.status()['pending'] >= self.policy['daily_target']:
                answer = 'STOP: daily target reached or reserved'
            else:
                self.db.execute('INSERT INTO email_resumes VALUES (?,?,?)',(key(url),item['gmail_message_id'],self.now))
                self.db.execute("UPDATE attempts SET state='pending',evidence='Continuing same application after matching email verification request' WHERE job_key=?",(key(url),))
                answer = 'GO'
            self.db.execute('COMMIT')
            return answer
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def block(self, url, seconds=3600, reason='site challenge or rate limit'):
        self.refresh()
        host = urlsplit(url).hostname
        self.db.execute('INSERT INTO blocks VALUES (?,?,?) ON CONFLICT(host) DO UPDATE SET until=max(until,excluded.until),reason=excluded.reason',
            (host,self.now+max(3600,seconds),reason))


def validate_personal_answers(cfg, policy):
    confirmed = policy.get('confirmed_personal_answers', {})
    sensitive = {
        'essential_functions': r'essential functions',
        'employment_restrictions': r'employment agreements|post.employment restrictions|non.compete',
        'start_date': r'when.*start|earliest.*start|start date',
        'notice_period': r'notice period',
    }
    for q in cfg.get('unmapped_required', []):
        for name, pattern in sensitive.items():
            if re.search(pattern, q.get('label',''), re.I) and name not in confirmed:
                return 'User answer needed: ' + q['label']
    return ''


def validate_review(review, policy):
    if not review.get('fit_reviewed') or not review.get('schedule_notes'):
        return 'Missing qualification and schedule review'
    if review.get('schedule_conflict') is not False:
        return 'Schedule must fit Monday-Friday 09:00-17:00 Pacific'
    wp = review.get('workplace')
    if wp == 'remote':
        return '' if review.get('ca_eligible') is True else 'Remote role must accept California residents'
    if wp in ('onsite','hybrid'):
        miles = review.get('distance_miles')
        if isinstance(miles,(int,float)) and not isinstance(miles,bool) and 0 <= miles <= policy['max_commute_miles'] and review.get('distance_evidence'):
            return ''
        return 'Verify worksite within the configured commute limit and save distance evidence'
    return 'Workplace must be reviewed'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['status','check','reserve','finish','block'])
    p.add_argument('--url',default='');p.add_argument('--company',default='');p.add_argument('--title',default='')
    p.add_argument('--batch',default=os.environ.get('JOBHUNT_BATCH_ID','manual'))
    p.add_argument('--confirmed',action='store_true');p.add_argument('--evidence',default='');p.add_argument('--proof',default='')
    p.add_argument('--seconds',type=int,default=3600)
    args=p.parse_args();g=Guard()
    if args.action=='status':print(json.dumps(g.status(args.batch),indent=2));return 0
    if args.action in ('check','reserve'):
        value=g.check(args.url,args.company,args.batch) if args.action=='check' else g.reserve(args.url,args.company,args.title,args.batch)
        print(value);return 0 if value=='GO' else 2
    if args.action=='finish':g.finish(args.url,args.confirmed,args.evidence,args.proof)
    if args.action=='block':g.block(args.url,args.seconds,args.evidence or 'site challenge/rate limit')
    print(json.dumps(g.status(args.batch)));return 0

if __name__=='__main__':raise SystemExit(main())
