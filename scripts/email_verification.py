"""Complete an application email OTP through its visible form, without logging codes."""
import datetime as dt
import json
import os
import re
import tempfile
import time
from pathlib import Path

EMAIL_NAMES = {'vardaspace': 'Varda Space Industries'}


def write_private_json(path, data):
    """Replace local handoff data atomically using an owner-only temporary file."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
        os.replace(temporary, path)
        if os.name != 'nt':
            path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def employer_name(page, cfg):
    title = page.title()
    if title.startswith('Job Application for ') and ' at ' in title:
        return title.rsplit(' at ', 1)[1].strip()
    return cfg.get('email_company') or EMAIL_NAMES.get(cfg['company'].casefold(), cfg['company'])


def matching_code(path, company, since=0, now=None):
    now = time.time() if now is None else now
    company = EMAIL_NAMES.get(company.casefold(), company)
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    candidates = []
    for item in data.get('codes', []):
        if item.get('used'):
            continue
        if item.get('sender', '').casefold() != 'no-reply@us.greenhouse-mail.io':
            continue
        if item.get('subject', '').casefold().strip() != f'security code for your application to {company}'.casefold():
            continue
        try:
            received = dt.datetime.fromisoformat(item['received_utc'].replace('Z', '+00:00')).timestamp()
            expires = item.get('expires_at_utc')
            if expires and dt.datetime.fromisoformat(expires.replace('Z', '+00:00')).timestamp() <= now:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        code = str(item.get('code', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9]{8}', code) or received < since or received > now + 60 or now - received > 3600:
            continue
        candidates.append((received, item))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def mark_used(path, item):
    path = Path(path)
    data = json.loads(path.read_text())
    for entry in data.get('codes', []):
        if entry.get('gmail_message_id') == item.get('gmail_message_id') and entry.get('code') == item['code']:
            entry['used'] = True
            entry.pop('code', None)
    write_private_json(path, data)


def complete_email_code(page, cfg, apps, submitted_at, timeout=240):
    """Return whether a matched code was entered and the same form resubmitted."""
    body = page.locator('body').inner_text().lower()
    if 'security code' not in body or 'verification code was sent' not in body:
        return False
    apps = Path(apps)
    path = apps / '_current_job_verification.json'
    request = apps / '_pending_email_verification.json'
    email_company = employer_name(page, cfg)
    write_private_json(request, {'company': cfg['company'], 'email_company': email_company,
        'expected_subject': 'Security code for your application to ' + email_company, 'title': cfg.get('title'),
        'url': page.url, 'requested_at_utc': dt.datetime.fromtimestamp(submitted_at,dt.timezone.utc).isoformat(),
        'state': 'waiting-for-code', 'code_file': str(path)})
    print('NEEDS_EMAIL_CODE: ' + cfg['company'] + ' | form remains open; read matching Gmail message into ' + str(path), flush=True)
    deadline = time.monotonic() + timeout
    item = None
    while time.monotonic() < deadline:
        item = matching_code(path, email_company, submitted_at - 15)
        if item:
            break
        page.wait_for_timeout(2000)
    if not item:
        print('EMAIL_CODE_TIMEOUT: no matching current message; application remains unconfirmed', flush=True)
        return False
    # Inspect the visible one-character code inputs used by Greenhouse's OTP form.
    single = page.locator('input[maxlength="1"]:visible')
    if single.count() == 8:
        for i, char in enumerate(item['code']):
            single.nth(i).fill(char)
    else:
        field = page.get_by_label(re.compile(r'^security code', re.I))
        if field.count() != 1 or not field.is_visible():
            print('EMAIL_CODE_FIELD_UNKNOWN: preserve pending application for inspection', flush=True)
            return False
        field.fill(item['code'])
    mark_used(path, item)
    button = page.get_by_role('button', name=re.compile(r'^(submit|submit application|resubmit|resubmit application)$',re.I))
    if button.count() != 1:
        print('EMAIL_CODE_SUBMIT_UNKNOWN: no unambiguous form submit', flush=True)
        return False
    button.click()
    write_private_json(request, {'company':cfg['company'],'url':cfg['url'],'state':'code-entered-awaiting-confirmation'})
    print('EMAIL_CODE_ENTERED: matching application resubmitted; checking confirmation', flush=True)
    return True
