import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import interview_qa as qa


def payload(**changes):
    data = dict(session_id='test-session', company='Fixture Employer', title='Analyst',
                url='https://example.test/job/1', stage='interview', phase='draft',
                source='test fixture', records=[dict(question='Tell me about a difficult issue?',
                                                    answer='First line.\nSecond line — exact wording.')])
    data.update(changes)
    return data


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def events(self):
        with sqlite3.connect(self.root / '_interview_qa.sqlite3') as db:
            events = db.execute('SELECT phase,records,note FROM events ORDER BY rowid').fetchall()
        db.close()
        return events

    def test_exact_text_and_revisions_survive_reopening(self):
        qa.record(payload(), self.root)
        qa.record(payload(phase='provided', records=[dict(question='Tell me about a difficult issue?',
                                                        answer='Corrected exact answer.')]), self.root)
        events = self.events()
        self.assertEqual(len(events), 2)
        self.assertEqual(json.loads(events[0][1])[0]['answer'], 'First line.\nSecond line — exact wording.')
        self.assertEqual(events[1][0], 'provided')
        report = (self.root / '_interview_qa.md').read_text(encoding='utf-8')
        self.assertIn('> Second line — exact wording.', report)
        self.assertIn('Corrected exact answer.', report)

    def test_unanswered_and_outcome_do_not_invent_an_answer(self):
        qa.record(payload(phase='observed', records=[dict(question='Desired salary?', answer=None)]), self.root)
        qa.outcome({'url':'https://example.test', 'company':'Fixture', 'title':'Analyst'},
                   self.root, 'test-session', False, 'No receipt')
        report = (self.root / '_interview_qa.md').read_text(encoding='utf-8')
        self.assertIn('[No answer recorded]', report)
        self.assertIn('UNCONFIRMED: No receipt', report)

    def test_sensitive_values_are_redacted(self):
        rows = [dict(field='otp', question='Security code', answer='DONTSTORE123'),
                dict(question='Social security number', answer='DONTSTORE456'),
                dict(question='Are you authorized to work?', answer='Yes')]
        qa.record(payload(records=rows), self.root)
        all_text = str(self.events()) + (self.root / '_interview_qa.md').read_text(encoding='utf-8')
        self.assertNotIn('DONTSTORE', all_text)
        self.assertIn('Yes', all_text)

    def test_missing_question_or_phase_rejected(self):
        with self.assertRaises(ValueError):
            qa.record(payload(records=[dict(answer='Unsupported')]), self.root)
        with self.assertRaises(ValueError):
            qa.record(payload(phase='sent-probably'), self.root)
        with self.assertRaises(ValueError):
            qa.record(payload(records=[]), self.root)

    def test_concurrent_events_survive_and_export_is_current(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: qa.record(payload(session_id='session-' + str(i)), self.root), range(12)))
        self.assertEqual(len(self.events()), 12)
        report = (self.root / '_interview_qa.md').read_text(encoding='utf-8')
        self.assertEqual(report.count('## Fixture Employer'), 12)


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, 'Browser fixture requires Playwright (available on runner VPS)')
class BrowserCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def read(self, html):
        self.page.set_content(html)
        return self.page.evaluate((qa.HERE / 'interview_qa_capture.js').read_text(encoding='utf-8'))

    def test_full_questions_text_and_real_options(self):
        question = 'Describe the most difficult production incident you investigated, including the steps you took, '
        question += 'what you learned, and the actual outcome for the customer.'
        rows = self.read(f'''<label for="q">{question}</label><textarea id="q">Exact answer.\nSecond line.</textarea>
            <label for="timezone">Time zone?</label><select id="timezone"><option value="pst" selected>Pacific</option></select>
            <label for="empty">Unanswered?</label><input id="empty">''')
        by_id = {r['field']: r for r in rows}
        self.assertEqual(by_id['q']['question'], question)
        self.assertEqual(by_id['q']['answer'], 'Exact answer.\nSecond line.')
        self.assertEqual(by_id['timezone']['answer'], ['Pacific'])
        self.assertEqual(by_id['empty']['answer_state'], 'unanswered')

    def test_radio_and_multiselect_capture_selected_labels(self):
        rows = self.read('''<fieldset><legend>Do you have work authorization?</legend>
            <label><input type="radio" name="work" value="1" checked>Yes</label>
            <label><input type="radio" name="work" value="0">No</label></fieldset>
            <fieldset><legend>Which tools have you used?</legend>
            <label><input type="checkbox" name="tools" checked>Python</label>
            <label><input type="checkbox" name="tools" checked>SQL</label></fieldset>''')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['question'], 'Do you have work authorization?')
        self.assertEqual(rows[0]['answer'], ['Yes'])
        self.assertEqual(rows[1]['answer'], ['Python', 'SQL'])

    def test_react_select_and_ashby_buttons(self):
        rows = self.read('''<label for="country">Country?</label><div class="select__control">
            <span class="select__single-value">United States</span><input id="country" role="combobox"></div>
            <label for="search">Uncommitted location?</label><div class="select__control">
            <input id="search" role="combobox" value="Boston"></div>
            <div data-field-path="sponsor"><label>Do you require sponsorship?</label>
            <button data-option="yes" aria-pressed="false">Yes</button>
            <button data-option="no" aria-pressed="true">No</button></div>''')
        by_id = {r['field']: r for r in rows}
        self.assertEqual(by_id['country']['answer'], ['United States'])
        self.assertEqual(by_id['search']['answer'], [])
        self.assertEqual(by_id['sponsor']['question'], 'Do you require sponsorship?')
        self.assertEqual(by_id['sponsor']['answer'], ['No'])

    def test_credentials_and_hidden_fields_are_not_captured(self):
        rows = self.read('''<label for="q">Years of experience?</label><input id="q" value="2">
            <label for="otp">Security code</label><input id="otp" value="SECRET">
            <input type="password" value="SECRET"><input type="hidden" name="token" value="SECRET">
            <label for="code">Code</label><input id="code" autocomplete="one-time-code" value="SECRET">
            <label style="display:none" for="invisible">Not asked</label><input style="display:none" id="invisible" value="SECRET">''')
        self.assertEqual(len(rows), 1)
        self.assertNotIn('SECRET', json.dumps(rows))

    def test_browser_capture_reaches_durable_journal(self):
        self.page.set_content('<label for="q">Why this role?</label><textarea id="q">I enjoy support.</textarea>')
        with tempfile.TemporaryDirectory() as root:
            qa.capture(self.page, {'company':'Fixture Employer', 'title':'Support', 'url':'https://example.test'},
                       root, 'filled', 'browser-session')
            report = (Path(root) / '_interview_qa.md').read_text(encoding='utf-8')
            self.assertIn('Why this role?', report)
            self.assertIn('I enjoy support.', report)
            self.assertIn('**filled**', report)


if __name__ == '__main__':
    unittest.main()
