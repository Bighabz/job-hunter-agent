#!/usr/bin/env python3
"""Workable public job-search discovery + stage-2 auto-triage.

Why this exists: blind Greenhouse slug-guessing is exhausted (see _run_log.md
2026-09-12) and the 54 tokens in portals.yml no longer yield eligible roles.
jobs.workable.com/api/v1/jobs is a real public search index over thousands of
SMB employers -- exactly the realistic admin/support/data-entry market -- and it
returns the FULL description + requirementsSection inline, so the schedule /
years / residency triage that used to need a second fetch per role happens for
free on the search response.

Output: a CLEAN vs FLAGGED split with the surrounding evidence text, same shape
as the /tmp/sweep5.py stage-2 triage that worked for Greenhouse.
"""
import json, re, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
      'Accept': 'application/json'}
API = 'https://jobs.workable.com/api/v1/jobs'

QUERIES = [
    'customer support', 'customer service representative', 'data entry',
    'administrative assistant', 'office assistant', 'help desk',
    'it support', 'operations associate', 'recruiting coordinator',
    'technical support', 'office coordinator', 'scheduler',
]

# 15 miles of ZIP 90247 (Gardena). Long Beach/Downey/Culver City are edge cases
# that still need per-req address evidence, so they are NOT auto-accepted here.
NEAR_90247 = ['gardena', 'torrance', 'carson', 'compton', 'hawthorne',
              'el segundo', 'lawndale', 'redondo beach', 'inglewood',
              'harbor city', 'lomita', 'manhattan beach', 'hermosa beach',
              'wilmington, ca', 'south gate']

SCHED = re.compile(r"(weekend|saturday|sunday|evening|overnight|night shift|"
                   r"graveyard|on[- ]call|24/7|24x7|rotating shift|shift work|"
                   r"holidays as needed|extended hours|flexible hours as|"
                   r"after[- ]hours|swing shift|2nd shift|3rd shift)", re.I)
# \best\b, not est\b: an unanchored "est\b" matches the tail of "request",
# "best" and "latest", which inflated the flagged list on the first run.
TZ = re.compile(r"(eastern time|eastern standard|\best\b|\bedt\b|central time|"
                r"\bcst\b|\bcdt\b|gmt[+-]|\bcet\b|philippines|manila|"
                r"india standard)", re.I)
YRS = re.compile(r"([3-9]|1\d)\s*\+?\s*(?:-\s*\d+\s*)?year", re.I)
RESID = re.compile(r"(must reside in|residents of|located in one of the "
                   r"following states|following states:)", re.I)
LANG = re.compile(r"(bilingual|fluen\w+ in (spanish|french|german|portuguese|"
                  r"mandarin)|native speaker)", re.I)
LIC = re.compile(r"(property & casualty|property and casualty|series 7|"
                 r"series 63|rn license|lvn|cna certif|cdl\b|notary|"
                 r"real estate license|insurance license)", re.I)
SCAM = re.compile(r"(we will ship|equipment will be shipped|wire transfer|"
                  r"cashier'?s check|telegram|whatsapp us|signing bonus paid|"
                  r"no experience necessary and no interview)", re.I)

TAG = [('SCHED', SCHED), ('TZ', TZ), ('YRS', YRS), ('RESID', RESID),
       ('LANG', LANG), ('LIC', LIC), ('SCAM', SCAM)]


def strip_html(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h or '', flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    h = (h.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#39;', "'")
          .replace('&quot;', '"').replace('&lt;', '<').replace('&gt;', '>'))
    return re.sub(r'\s+', ' ', h).strip()


def fetch(url):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=30).read())


def search(query, pages=2, location='United States'):
    out, token = [], None
    for _ in range(pages):
        p = {'query': query}
        if location:
            p['location'] = location
        if token:
            p['pageToken'] = token
        try:
            d = fetch(API + '?' + urllib.parse.urlencode(p))
        except Exception as e:                      # noqa: BLE001
            print(f'  ! {query}: {e!r}', file=sys.stderr)
            break
        out += d.get('jobs', [])
        token = d.get('nextPageToken')
        if not token:
            break
        time.sleep(1.2)                             # one host, polite pacing
    return out


def geo_ok(j):
    loc = (str(j.get('locations', '')) + ' ' + str(j.get('location', ''))).lower()
    if j.get('workplace') == 'remote' or 'telecommute' in loc:
        return 'remote' if 'united states' in loc or 'usa' in loc else None
    if any(c in loc for c in NEAR_90247):
        return j.get('workplace') or 'onsite'
    return None


def triage(j):
    text = strip_html(j.get('description', '')) + ' \n' + \
           strip_html(j.get('requirementsSection', ''))
    flags = []
    for name, rx in TAG:
        m = rx.search(text)
        if m:
            s = max(0, m.start() - 90)
            flags.append(f'{name}: ...{text[s:m.end() + 110]}...')
    return flags, text


def main():
    seen, clean, flagged = set(), [], []
    for q in QUERIES:
        jobs = search(q)
        print(f'{q}: {len(jobs)} raw', file=sys.stderr)
        for j in jobs:
            if j['id'] in seen:
                continue
            seen.add(j['id'])
            wp = geo_ok(j)
            if not wp:
                continue
            if (j.get('employmentType') or '').lower() in ('internship',):
                continue
            flags, text = triage(j)
            rec = {'title': j['title'],
                   'company': (eval(j['company']) if isinstance(j['company'], str)
                               else j['company']).get('title'),
                   'workplace': wp, 'locations': j.get('locations'),
                   'employmentType': j.get('employmentType'),
                   'url': j['url'], 'created': j.get('created'),
                   'flags': flags, 'text': text}
            (flagged if flags else clean).append(rec)
        time.sleep(1.2)

    print(f'\n===== CLEAN: {len(clean)} =====')
    for r in clean:
        print(f"- {r['company']} | {r['title']} | {r['workplace']} | "
              f"{r['locations']} | {r['employmentType']} | {r['url']}")
    print(f'\n===== FLAGGED: {len(flagged)} =====')
    for r in flagged:
        print(f"- {r['company']} | {r['title']} | {[f.split(':')[0] for f in r['flags']]}")
    json.dump({'clean': clean, 'flagged': flagged},
              open('/tmp/workable_triage.json', 'w'), indent=1)
    print('\nwrote /tmp/workable_triage.json', file=sys.stderr)


if __name__ == '__main__':
    main()
