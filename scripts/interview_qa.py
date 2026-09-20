"""Durable question/answer journal for job forms and interview exchanges.

No networking or submissions. SQLite is authoritative; Markdown is a readable view.
"""
import argparse
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid

HERE = Path(__file__).resolve().parent
PHASES = {'observed', 'draft', 'filled', 'submitting', 'provided', 'confirmed',
          'unconfirmed', 'skipped', 'outcome'}
SENSITIVE = re.compile(
    r'password|passcode|\bone[ _-]?time\b|\botp\b|verification.?code|security.?code|'
    r'auth.?token|captcha|\bssn\b|social.security.(?:number|#)|'
    r'bank.account|routing.number|credit.card|card.number', re.I)


def applications():
    return Path(os.environ.get('JOBHUNT_APPLICATIONS', str(HERE.parent / 'applications')))


def clean_records(records):
    result = []
    for item in records:
        question = str(item.get('question', '')).strip()
        if not question:
            raise ValueError('Every record requires the full question or an explicit unlabeled-field marker')
        row = {k: item[k] for k in ('field', 'question', 'answer', 'options', 'required',
                                  'answer_state', 'label_source') if k in item}
        row['question'] = question
        row.setdefault('answer', None)
        if SENSITIVE.search(question + ' ' + str(row.get('field', ''))):
            row['answer'] = '[REDACTED: credential or financial identifier]'
            row.pop('options', None)
            row['answer_state'] = 'redacted'
        result.append(row)
    return result


def connect(root):
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / '_interview_qa.sqlite3', timeout=30)
    db.execute('''CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, session_id TEXT NOT NULL,
        company TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
        batch TEXT NOT NULL, stage TEXT NOT NULL, phase TEXT NOT NULL,
        source TEXT NOT NULL, records TEXT NOT NULL, note TEXT NOT NULL)''')
    return db


def render(db, root):
    # Serialize readers/writers through SQLite so concurrent exports cannot replace
    # a newer view with an older snapshot. The database remains the durable record.
    db.execute('BEGIN IMMEDIATE')
    tmp = root / ('_interview_qa.' + uuid.uuid4().hex + '.tmp')
    try:
        parts = ['# Job interview and screening questions & answers\n',
                 'Recording enabled September 18, 2026. Times are UTC. '
                 'Draft/filled answers are not proof of submission. '
                 'Submissions are confirmed only when explicitly marked.\n']
        for event in db.execute('SELECT * FROM events ORDER BY rowid'):
            (eid, stamp, session, company, title, url, batch, stage, phase,
             source, records, note) = event
            parts += [f'## {company} — {title}\n',
                      f'{stamp} | {stage} | **{phase}** | session `{session}`\n',
                      f'Job/source: {url}\n', f'Capture: {source} | batch: {batch} | event: `{eid}`\n']
            if note:
                parts.append(f'{note}\n')
            for row in json.loads(records):
                answer = row.get('answer')
                shown = json.dumps(answer, ensure_ascii=False) if not isinstance(answer, str) else answer
                if answer is None or answer == '' or answer == []:
                    shown = '[No answer recorded]'
                # Blockquotes preserve multiline wording without turning embedded
                # employer/user text into report headings.
                parts += ['**Question**\n\n> ' + row['question'].replace('\n', '\n> ') + '\n',
                          '**Answer**\n\n> ' + shown.replace('\n', '\n> ') + '\n',
                          f"State: {row.get('answer_state', phase)}; field: `{row.get('field', '')}`\n"]
                if row.get('options'):
                    parts.append('Choices: ' + json.dumps(row['options'], ensure_ascii=False) + '\n')
        tmp.write_text('\n'.join(parts), encoding='utf-8')
        os.replace(tmp, root / '_interview_qa.md')
        db.commit()
    except BaseException:
        db.rollback()
        tmp.unlink(missing_ok=True)
        raise


def record(payload, root=None):
    root = Path(root) if root is not None else applications()
    phase = payload.get('phase', 'draft')
    if phase not in PHASES:
        raise ValueError('Unknown phase: ' + phase)
    for field in ('session_id', 'company', 'title', 'stage', 'source'):
        if not str(payload.get(field, '')).strip():
            raise ValueError('Missing ' + field)
    rows = clean_records(payload.get('records', []))
    if not rows and phase != 'outcome':
        raise ValueError('No question/answer records; inspect the page and log manually')
    event_id = uuid.uuid4().hex
    with closing(connect(root)) as db:
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (
            event_id, dt.datetime.now(dt.timezone.utc).isoformat(),
            payload['session_id'], payload['company'], payload['title'], payload.get('url', ''),
            payload.get('batch', os.environ.get('JOBHUNT_BATCH_ID', 'manual')),
            payload['stage'], phase, payload['source'], json.dumps(rows, ensure_ascii=False),
            str(payload.get('note', ''))))
        db.commit()
        render(db, root)
    return event_id


def capture(page, cfg, root, phase, session_id):
    rows = page.evaluate((HERE / 'interview_qa_capture.js').read_text(encoding='utf-8'))
    return record({
        'session_id': session_id,
        'company': cfg.get('company') or '[company not supplied]',
        'title': cfg.get('title') or '[role not supplied]',
        'url': cfg['url'], 'stage': 'application_screening', 'phase': phase,
        'source': 'browser form readback', 'records': rows,
    }, root)


def outcome(cfg, root, session_id, confirmed, evidence):
    return record({
        'session_id': session_id,
        'company': cfg.get('company') or '[company not supplied]',
        'title': cfg.get('title') or '[role not supplied]',
        'url': cfg['url'], 'stage': 'application_screening', 'phase': 'outcome',
        'source': 'application helper confirmation check', 'records': [],
        'note': ('CONFIRMED' if confirmed else 'UNCONFIRMED') + ': ' + evidence,
    }, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['record', 'init', 'export', 'status'])
    parser.add_argument('--input', help='JSON file, or - for stdin (record only)')
    parser.add_argument('--directory', type=Path, default=applications())
    args = parser.parse_args()
    if args.command == 'record':
        if not args.input:
            parser.error('record requires --input')
        raw = sys.stdin.read() if args.input == '-' else Path(args.input).read_text(encoding='utf-8-sig')
        print(json.dumps({'event_id': record(json.loads(raw), args.directory),
                          'journal': str(args.directory / '_interview_qa.md')}))
    else:
        with closing(connect(args.directory)) as db:
            if args.command in ('init', 'export'):
                render(db, args.directory)
            print(json.dumps({'events': db.execute('SELECT count(*) FROM events').fetchone()[0],
                              'journal': str(args.directory / '_interview_qa.md')}))


if __name__ == '__main__':
    main()
