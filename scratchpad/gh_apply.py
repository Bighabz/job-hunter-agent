"""Generic Greenhouse (job-boards.greenhouse.io) applier via Playwright.

Bypasses the Chrome extension entirely (own temp profile, real Chrome channel),
which is what makes it work when the MCP extension has no site access.

Usage:
  python gh_apply.py <config.json>            # fill + inspect, DO NOT submit
  python gh_apply.py <config.json> --submit   # fill + submit + confirm
"""
import json, os, re, sys, time, pathlib, uuid
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
from external_guard import Guard, validate_review, validate_personal_answers, hostname_is
from email_verification import complete_email_code
from interview_qa import capture as capture_qa, outcome as qa_outcome

# Keep the resume and browser state in configurable, private locations.
_WIN = os.name == "nt"
RESUME = os.environ.get("HJ_RESUME") or str(pathlib.Path(__file__).resolve().parent.parent / "master" / "resume.pdf")
_DEFAULT_PROFILE = os.environ.get("JOBHUNT_BROWSER_PROFILE") or str(pathlib.Path.home() / ".cache" / "job-hunter" / "browser")

def log(*a): print(*a, flush=True)

def main():
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    do_submit = "--submit" in sys.argv
    resume_verification = "--resume-email-verification" in sys.argv
    url = cfg["url"]
    guard = Guard()
    batch = os.environ.get('JOBHUNT_BATCH_ID', 'manual')
    company = cfg.get('company', '')
    qa_session_id = cfg.get('qa_session_id') or f'{batch}-{uuid.uuid4().hex}'
    if do_submit:
        review_error = validate_review(cfg.get('review', {}), guard.policy) or validate_personal_answers(cfg, guard.policy)
        decision = 'GO' if resume_verification else guard.check(url, company, batch)
        if review_error or decision != 'GO':
            log('NOT SUBMITTING:', review_error or decision)
            return 2
    text_answers = cfg.get("text", {})     # {field_id_or_name: value}
    select_answers = cfg.get("selects", {})# {field_id_or_name: option_label}
    unanswered = [q for q in cfg.get("unmapped_required", [])
                  if not any(q["name"] in cfg.get(k, {})
                             for k in ("text", "selects", "checks", "type_text", "typeaheads"))]
    if do_submit and unanswered:
        log("NOT SUBMITTING: required questions have no verified answers", unanswered)
        return 2
    tmp = pathlib.Path(cfg.get("profile", _DEFAULT_PROFILE))
    tmp.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(tmp), channel="chrome", headless=False, no_viewport=True,
            args=[] if _WIN else ["--no-sandbox"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        # 2026-09-12, apply.workable.com: a [data-ui=cookie-consent] dialog plus its
        # full-page [data-ui=backdrop] sit over the form and intercept EVERY click, so
        # radio groups and the submit button retry-loop until Playwright times out.
        # Dismiss the consent dialog before touching anything (it burned the PracticeTek
        # RevEHR req). Same class as the Lever hidden-submit-button bug: the element reads
        # "visible, enabled and stable" and is still unclickable.
        for sel in ('[data-ui="cookie-consent"] button[data-ui="cookie-consent-accept"]',
                    '[data-ui="cookie-consent"] button:has-text("Accept")',
                    '[data-ui="cookie-consent"] button:has-text("Got it")',
                    '[data-ui="cookie-consent"] button'):
            try:
                b = page.locator(sel).first
                if b.count() and b.is_visible():
                    b.click(timeout=4000)
                    page.wait_for_timeout(800)
                    log(f"[cookie] dismissed via {sel}")
                    break
            except Exception:
                continue
        try:
            if page.locator('[data-ui="cookie-consent"],[data-ui="backdrop"]').count():
                page.evaluate("""() => document.querySelectorAll(
                    '[data-ui=cookie-consent],[data-ui=backdrop]').forEach(e => e.remove())""")
                log("[cookie] consent dialog/backdrop removed from the DOM")
        except Exception:
            pass

        page_text = page.locator('body').inner_text().lower()
        if any(t in page_text for t in ('verify you are human', 'complete the captcha', 'unusual traffic', 'too many requests', 'access denied')):
            guard.block(url, reason='visible verification challenge or rate limit')
            log('STOP: visible verification challenge or rate limit; source cooldown recorded')
            ctx.close()
            return 2

        # ---- dump form fields so we can see what we're dealing with
        fields = page.evaluate("""() => {
          // 2026-09-12: Ashby renders Location comboboxes and yes/no checkbox groups with NO
          // label[for] and no wrapping <label>, so they used to dump as blank and a "bad:0"
          // prefill looked clean while two required fields were empty (astra, one burned req).
          // Fall back to the field's own container heading, which is the real visible label.
          const container = e => e.closest(
            '[class*="field-entry"],[class*="FieldEntry"],[class*="_field"],fieldset,[role=group]');
          const out = [];
          document.querySelectorAll('input,textarea,select').forEach(e => {
            if (e.type === 'hidden' || e.name === 'g-recaptcha-response') return;
            let lab = '', src = '';
            if (e.id) { const l = document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if (l) { lab = l.innerText.trim(); src='for'; } }
            if (!lab && e.closest('label')) { lab = e.closest('label').innerText.trim(); src='wrap'; }
            if (!lab) { lab = (e.getAttribute('aria-label')||'').trim(); if (lab) src='aria'; }
            if (!lab) {
              const c = container(e);
              if (c) { lab = (c.innerText||'').trim().split('\\n')[0].trim(); src='container'; }
            }
            out.push({tag:e.tagName.toLowerCase(), type:e.type||'', id:e.id||'', name:e.name||'',
                      role:e.getAttribute('role')||'',
                      req:e.required||e.getAttribute('aria-required')==='true'||/\\*\\s*$/.test(lab),
                      labelSrc:src, label:lab.slice(0,90)});
          });
          return out;
        }""")
        log("=== FORM FIELDS ===")
        for f in fields: log(" ", f)
        capture_qa(page, cfg, guard.ledger.parent, 'observed', qa_session_id)

        # ---- pre-pass clicks by VISIBLE TEXT (2026-09-12)
        # Greenhouse renders some required Cover Letter fields as input[type=file] and keeps
        # cover_letter_text hidden until an "Enter manually" button is pressed. No positional
        # selectors: match the button's own visible label, which is the public schema.
        # cfg["clicks"] = ["Enter manually", {"text": "Enter manually", "near": "Cover Letter"}]
        # A bare string clicks the first match. Use "near" when the same label appears more than
        # once (Greenhouse renders one "Enter manually" per attachment field): the button is only
        # taken if an ancestor container also carries the "near" label text.
        for spec in cfg.get("clicks", []):
            if isinstance(spec, str):
                spec = {"text": spec}
            want, near = spec["text"], spec.get("near", "")
            try:
                res = page.evaluate("""(a) => {
                  const t = a.text.toLowerCase(), near = (a.near || '').toLowerCase();
                  const cands = [...document.querySelectorAll('button,a,[role=button]')]
                      .filter(b => (b.innerText || '').trim().toLowerCase().includes(t));
                  for (const b of cands) {
                    if (!near) { b.click(); return 'clicked'; }
                    let n = b;
                    for (let d = 0; d < 6 && n; d++) {
                      n = n.parentElement;
                      if (n && (n.innerText || '').toLowerCase().includes(near)) { b.click(); return 'clicked'; }
                    }
                  }
                  return cands.length ? 'no-near-match' : 'not-found';
                }""", {"text": want, "near": near})
                page.wait_for_timeout(1200)
                log(f"[click] {want!r} near={near!r} -> {res}")
            except Exception as e:
                log(f"[click] FAIL {want!r}: {e}")

        # ---- text fields
        for key, val in text_answers.items():
            for sel in (f'#{key}', f'[name="{key}"]', f'[id="{key}"]'):
                try:
                    el = page.locator(sel).first
                    if el.count() and el.is_visible():
                        el.fill(str(val)); log(f"[text] {key} <- {val}"); break
                except Exception:
                    continue
            else:
                log(f"[text] MISS {key}")

        # ---- react-select comboboxes
        for key, want in select_answers.items():
            try:
                combo = page.locator(f'input[role=combobox][id="{key}"], input[role=combobox][name="{key}"], select[id="{key}"], select[name="{key}"]').first
                if not combo.count():
                    log(f"[select] MISS {key}"); continue
                if combo.evaluate("e => e.tagName.toLowerCase()") == "select":
                    combo.select_option(label=want); log(f"[select-native] {key} <- {want}"); continue
                ctrl = combo.locator("xpath=ancestor::*[contains(@class,'select__control')][1]")
                (ctrl if ctrl.count() else combo).click()
                page.wait_for_timeout(700)
                menu = page.locator(".select__menu [role=option]")
                texts = menu.all_inner_texts()
                # 2026-09-17: the long country list renders its rows in .select__menu-list
                # WITHOUT role=option (same shape as the async school--0 typeahead). The
                # role-based read came back empty, so "NO OPTION for country" fired with
                # opts=[] and the field silently stayed blank. Fall back to the menu rows.
                if not texts:
                    menu = page.locator(".select__menu-list > *")
                    texts = menu.all_inner_texts()
                idx = next((i for i, t in enumerate(texts) if t.strip() == want), None)
                if idx is None:
                    idx = next((i for i, t in enumerate(texts) if t.strip().startswith(want)), None)
                if idx is None:
                    idx = next((i for i, t in enumerate(texts) if want.lower() in t.strip().lower()), None)
                if idx is None:
                    log(f"[select] NO OPTION for {key} want={want!r} opts={texts}"); continue
                menu.nth(idx).click()
                page.wait_for_timeout(500)
                log(f"[select] {key} <- {want}")
            except Exception as e:
                log(f"[select] FAIL {key}: {e}")

        # ---- checkbox / radio groups (custom boards: Twilio, GitLab)
        # cfg["checks"] = {"<input name or id prefix>": "<label substring>" | [subs...]}
        # A key starting with "*" matches on the name/id SUFFIX instead: Ashby prefixes every
        # group name with a per-page-load form uuid, so only the trailing field id is stable.
        # 2026-09-18, jobs.lever.co (mashgin): this whole stage used to run through Playwright
        # locators and check(force=True). Lever's radios are visually hidden, so the forced
        # click does NOT throw - it dispatches a REAL mouse click at the element's degenerate
        # box, which landed on the site header link and NAVIGATED the form away to the job
        # list. Every later field then read empty and the resume "vanished" - the "100MB
        # upload" red herring. A CSS-selector precheck was not enough either: matching these
        # names through CSS attribute selectors (they contain [brackets] and per-form uuids)
        # is fragile and cost two 30s actionability timeouts per group.
        # So: do the whole group in ONE page.evaluate. Match names in JS (no CSS escaping),
        # read labels, and tick via the associated label's synthetic .click() - which a real
        # mouse never performs, so it cannot land on anything else. Never navigates.
        for key, want in cfg.get("checks", {}).items():
            wants = want if isinstance(want, list) else [want]
            try:
                res = page.evaluate("""(a) => {
                  const suffix = a.key.startsWith('*');
                  const k = suffix ? a.key.slice(1) : a.key;
                  const boxes = [...document.querySelectorAll('input[type=checkbox],input[type=radio]')]
                    .filter(e => suffix ? (e.name || '').endsWith(k)
                                        : ((e.name || '') === k || (e.id || '').startsWith(k)));
                  if (!boxes.length) return {n: 0, hits: []};
                  const labelOf = e => {
                    let l = e.id ? document.querySelector('label[for="' + CSS.escape(e.id) + '"]') : null;
                    if (!l) l = e.closest('label');
                    return (l ? l.innerText : '').trim();
                  };
                  const labels = boxes.map(labelOf);
                  const wl = a.wants.map(w => w.trim().toLowerCase());
                  // exact label match wins. Substring alone ticked BOTH "Male" and "Female"
                  // for want="Male" (2026-09-12, airbyte EEO), silently corrupting the answer.
                  const exact = labels.map((l, i) => wl.includes(l.trim().toLowerCase()) ? i : -1)
                                      .filter(i => i >= 0);
                  let idxs = exact.length
                    ? exact
                    : labels.map((l, i) => wl.some(w => l.toLowerCase().includes(w)) ? i : -1)
                            .filter(i => i >= 0);
                  let sole = false;
                  if (!idxs.length && boxes.length === 1) { idxs = [0]; sole = true; }
                  const hits = [];
                  for (const i of idxs) {
                    const e = boxes[i];
                    const l = e.id ? document.querySelector('label[for="' + CSS.escape(e.id) + '"]')
                                   : e.closest('label');
                    if (l) l.click();
                    if (!e.checked) {
                      e.checked = true;
                      e.dispatchEvent(new Event('input', {bubbles: true}));
                      e.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                    hits.push({label: labels[i].slice(0, 45), checked: e.checked});
                  }
                  return {n: boxes.length, hits, sole, labels: labels.map(l => l.slice(0, 45))};
                }""", {"key": key, "wants": wants})
                if not res["n"]:
                    log(f"[check] MISS {key}")
                elif not res["hits"]:
                    log(f"[check] NO OPTION {key} want={wants} opts={res['labels']}")
                else:
                    for h in res["hits"]:
                        log(f"[check] {key} <- {h['label']!r}"
                            f"{' (sole box)' if res.get('sole') else ''}"
                            f"{'' if h['checked'] else ' BUT STILL UNCHECKED'}")
                page.wait_for_timeout(300)
            except Exception as e:
                log(f"[check] FAIL {key}: {e}")
        # a stray real click that navigates the form away used to masquerade as a missing
        # resume field; fail loudly on the URL instead.
        if cfg.get("checks") and page.url.split("?")[0].rstrip("/") != url.split("?")[0].rstrip("/"):
            log(f"STOP: form navigated away during the checks stage: {page.url}")
            ctx.close()
            return 2

        # ---- Ashby yes/no toggles (2026-09-12, Vultr)
        # Ashby does NOT render these as checkboxes or radios. Each question is a
        # <div data-field-path="<uuid>"> holding two <button data-option="yes|no" aria-pressed>.
        # The old "checks" path found a hidden input, failed .check() with "not visible", and
        # left three REQUIRED questions silently unanswered behind a clean bad:0 read.
        # cfg["yesno"] = {"<field-path uuid>": "yes" | "no"}
        hard_errors = []
        for path, want in cfg.get("yesno", {}).items():
            try:
                sel = f'[data-field-path="{path}"] button[data-option="{want.lower()}"]'
                btn_yn = page.locator(sel).first
                if not btn_yn.count():
                    log(f"[yesno] MISS {path}")
                    hard_errors.append(f"yesno {path}: no button[data-option={want!r}]")
                    continue
                btn_yn.click()
                page.wait_for_timeout(400)
                pressed = btn_yn.get_attribute("aria-pressed")
                log(f"[yesno] {path[:8]} <- {want} (aria-pressed={pressed})")
                if pressed != "true":
                    hard_errors.append(f"yesno {path}: click did not set aria-pressed (got {pressed})")
            except Exception as e:
                log(f"[yesno] FAIL {path}: {e}")
                hard_errors.append(f"yesno {path}: {e}")

        # ---- async typeaheads (location / school): type, wait for options, pick
        # 2026-09-12 (Yugabyte): a "no options for school--0" line used to be advisory, so a
        # silently-empty required education field still reached submit with a clean bad:0 read
        # and burned the req on server-side validation. Any typeahead that does not commit a
        # value is now a HARD pre-submit stop.
        for key, spec in cfg.get("typeaheads", {}).items():
            try:
                combo = page.locator(f'input[role=combobox][id="{key}"]').first
                if not combo.count():
                    log(f"[type-ahead] MISS {key}")
                    hard_errors.append(f"typeahead {key}: field not found")
                    continue
                combo.click()
                combo.type(spec["type"], delay=90)
                page.wait_for_timeout(2500)
                # 2026-09-16 (Faraday Future): Greenhouse's ASYNC typeaheads (school--0,
                # discipline--0) render their fetched rows in .select__menu-list WITHOUT a
                # role=option attribute, so the role-based locator saw zero rows while the
                # menu was visibly populated and the field was reported as a hard stop. The
                # static lists (degree--0) do carry role=option. Fall back to the menu-list
                # children when the role selector comes back empty.
                # 2026-09-17 (carrotfertility, maxwell): at 2.5s the async menu often still
                # holds a single "Loading..." row. That read was treated as the final option
                # list, so a perfectly fillable school--0 became a hard pre-submit stop and
                # the job was skipped. Poll for up to 10s more until real rows arrive.
                def read_menu():
                    t = page.locator(".select__menu [role=option]").all_inner_texts()
                    if t:
                        return page.locator(".select__menu [role=option]"), t
                    return (page.locator(".select__menu-list > *"),
                            page.locator(".select__menu-list > *").all_inner_texts())

                menu, texts = read_menu()
                for _ in range(10):
                    if texts and not all(re.match(r'\s*loading', t, re.I) for t in texts):
                        break
                    page.wait_for_timeout(1000)
                    menu, texts = read_menu()
                want = spec.get("pick", spec["type"])
                idx = next((i for i, t in enumerate(texts) if t.strip() == want), None)
                if idx is None:
                    idx = next((i for i, t in enumerate(texts) if want.lower() in t.strip().lower()), None)
                if idx is None:
                    log(f"[type-ahead] no options for {key}")
                    hard_errors.append(f"typeahead {key}: no option matched {want!r} (saw {texts[:6]})")
                    continue
                log(f"[type-ahead] {key} <- {texts[idx][:60]!r}")
                menu.nth(idx).click()
                page.wait_for_timeout(600)
            except Exception as e:
                log(f"[type-ahead] FAIL {key}: {e}")
                hard_errors.append(f"typeahead {key}: {e}")

        # ---- generic click/type/pick (Ashby comboboxes have no id; give a CSS selector)
        # cfg["pickers"] = [{"selector": "...", "type": "Gardena", "pick": "Gardena, CA"}]
        for spec in cfg.get("pickers", []):
            try:
                el = page.locator(spec["selector"]).first
                if not el.count():
                    log(f"[picker] MISS {spec['selector'][:40]}"); continue
                # react-select paints a placeholder div over the input, which swallows the
                # click (Pinpoint boards, 2026-09-07). Click the control wrapper instead.
                ctrl = el.locator("xpath=ancestor::*[contains(@class,'select__control')][1]")
                (ctrl if ctrl.count() else el).click()
                el.type(spec["type"], delay=90)
                page.wait_for_timeout(2500)
                # some react-select builds drop role=option; match the class too
                opts = page.locator('[role=option], [class*="__option"]')
                texts = opts.all_inner_texts()
                want = spec.get("pick", spec["type"]).lower()
                idx = next((i for i, t in enumerate(texts) if want in t.strip().lower()), None)
                if idx is None:
                    log(f"[picker] no options for {spec['selector'][:40]}"); continue
                log(f"[picker] <- {texts[idx][:60]!r}")
                opts.nth(idx).click(); page.wait_for_timeout(700)
            except Exception as e:
                log(f"[picker] FAIL {spec.get('selector','?')[:40]}: {e}")

        # ---- keyboard-typed text (controlled inputs that ignore .fill())
        for key, val in cfg.get("type_text", {}).items():
            try:
                # [id="..."] not #id: Ashby field ids start with a digit, which is not a valid
                # CSS id selector and makes the whole comma-joined selector throw.
                el = page.locator(f'[id="{key}"], [name="{key}"]').first
                el.click(); el.press("Control+a")
                # long essays at 45ms/char blow the 30s default timeout (airbyte, 2026-09-12)
                v = str(val)
                el.type(v, delay=45 if len(v) < 300 else 6, timeout=180000)
                page.wait_for_timeout(300)
                log(f"[type_text] {key} <- {str(val)[:40]}")
            except Exception as e:
                log(f"[type_text] FAIL {key}: {e}")

        # ---- resume (real disk path; no base64, no OS picker)
        # LAST on purpose: Ashby re-renders the form when pickers/type_text commit,
        # which silently drops an already-attached file (2026-08-25, Apex board).
        try:
            # 2026-09-13, apply.workable.com (dane-street-llc): some boards render an
            # OPTIONAL "Photo" upload ABOVE the required Resume upload, so both .first and
            # 'text=Choose file' grabbed the Photo dropzone. The resume landed in the photo
            # field, the resume chip never painted, and the submit was correctly refused.
            # Target the REQUIRED file input; fall back to .first when none is marked.
            req_file_id = page.evaluate("""() => {
                const f = [...document.querySelectorAll('input[type=file]')].find(
                    e => e.required || e.getAttribute('aria-required') === 'true');
                return f ? (f.id || '') : '';
            }""")
            fi = (page.locator(f'input[type=file][id="{req_file_id}"]').first
                  if req_file_id else page.locator('input[type=file]').first)
            # 2026-09-12, apply.workable.com: set_input_files lands the file in the input's
            # FileList (so fileInputNames reads clean) but Workable's uploader never sees it -
            # submit then fails with "Please select a file." and NO aria-invalid and NO .error
            # node, so the run looks like a silent no-op click. It burned the SMB Team req.
            # Driving the page's own "Choose file" control through the file-chooser event is
            # the app's real code path and registers the upload. Same failure class as the
            # Lever hidden-submit-button and the Workable cookie backdrop: the element reads
            # attached/visible/enabled and the framework state is still empty.
            used_chooser = False
            # 2026-09-18, jobs.lever.co (voltus): the identical failure to Workable.
            # set_input_files filled the FileList (fileInputNames clean, bad:0, textChip
            # False) but Lever's own uploader never ran, so its client-side validator read
            # an undefined parsed size and the submit died on "File exceeds the maximum
            # upload size of 100MB" for a 54KB PDF. Driving the visible ATTACH RESUME/CV
            # control through the file-chooser event is Lever's real code path.
            if hostname_is(url, 'workable.com') or hostname_is(url, 'lever.co'):
                sels = ([f'label[for="{req_file_id}"]'] if req_file_id else []) + [
                    'label[for="resume-upload-input"]', 'text=ATTACH RESUME/CV',
                    'text=Choose file', '[data-ui="dropzone"]', 'label[for^="input_files_input"]']
                for sel in sels:
                    try:
                        trg = page.locator(sel).first
                        if not trg.count() or not trg.is_visible():
                            continue
                        with page.expect_file_chooser(timeout=8000) as fc:
                            trg.click()
                        fc.value.set_files(RESUME)
                        used_chooser = True
                        log(f"[resume] file chooser via {sel}")
                        break
                    except Exception:
                        continue
            if not used_chooser:
                fi.set_input_files(RESUME)
            # Lever parses the PDF server-side and only paints the filename chip when that
            # returns ("Analyzing resume..." -> filename), which is slower than Greenhouse's
            # instant local chip. Let a board override the wait rather than raising it for all.
            page.wait_for_timeout(int(cfg.get("resume_wait_ms", 3000)))
            log("[resume] set_input_files ok")
        except Exception as e:
            log("[resume] FAIL", e)

        page.wait_for_timeout(1500)
        # resumeChip: Greenhouse paints the filename into the page, but Lever renders the
        # attached file only inside the <input type=file> FileList and a JS-managed widget.
        # input.files[0].name is the authoritative "the browser will upload this" evidence,
        # so accept either - but never accept "no file anywhere" (2026-09-12, Lever).
        state = page.evaluate("""() => {
            const fi = [...document.querySelectorAll('input[type=file]')];
            const names = fi.flatMap(e => [...(e.files || [])].map(f => f.name));
            return {
                bad: document.querySelectorAll('[aria-invalid="true"]').length,
                resumeChip: /HJ_Resume\.pdf/i.test(document.body.innerText)
                            || names.some(n => /HJ_Resume\.pdf/i.test(n)),
                // 2026-09-18: Lever's chip is styled text-transform:uppercase and innerText
                // reports the TRANSFORMED text, so the filename reads "HJ_RESUME.PDF".
                // The case-sensitive regex read that painted chip as "no chip" and cost a
                // whole batch chasing a non-existent upload bug. Match case-insensitively.
                textChip: /HJ_Resume\.pdf/i.test(document.body.innerText),
                fileInputNames: names,
            };
        }""")
        # On Workable the FileList alone is NOT evidence the upload registered (see the
        # resume block above), so demand the painted filename chip before spending a
        # guard reservation.
        if (hostname_is(url, 'workable.com') or hostname_is(url, 'lever.co')) and not state.get("textChip"):
            state["resumeChip"] = False
        log("=== STATE ===", state)
        page.screenshot(path=str(tmp / "prefill.png"))
        capture_qa(page, cfg, guard.ledger.parent, 'filled', qa_session_id)

        if "--diag" in sys.argv:
            diag = page.evaluate("""() => {
              const out=[];
              document.querySelectorAll('input,textarea,select').forEach(e=>{
                if(e.type==='hidden') return;
                const req = e.required || e.getAttribute('aria-required')==='true';
                if(!req) return;
                let lab=''; if(e.id){const l=document.querySelector(`label[for="${CSS.escape(e.id)}"]`); if(l) lab=l.innerText.trim();}
                if(!lab && e.closest('label')) lab=e.closest('label').innerText.trim();
                out.push({id:e.id||'(none)', role:e.getAttribute('role')||'', label:lab.slice(0,70),
                          val:(e.value||'').slice(0,40), empty:!(e.value||'').trim(),
                          invalid:e.getAttribute('aria-invalid')==='true'});
              });
              return out;
            }""")
            sel = page.evaluate("""() => {
              const out=[];
              document.querySelectorAll('input[role=combobox]').forEach(e=>{
                const wrap = e.closest('.select__control') ? e.closest('.select__control').parentElement : e.parentElement;
                const single = wrap ? wrap.querySelector('.select__single-value') : null;
                const multi = wrap ? [...wrap.querySelectorAll('.select__multi-value')].map(m=>m.innerText.trim()) : [];
                out.push({id:e.id||'(none)', chosen: single? single.innerText.trim() : (multi.length? multi.join('; ') : '(NONE)')});
              });
              return out;
            }""")
            radios = page.evaluate("""() => {
              const groups = {};
              document.querySelectorAll('input[type=radio],input[type=checkbox]').forEach(e => {
                const g = (e.name || '(anon)').slice(-12);
                let l = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
                if (!l) l = e.closest('label');
                const lab = (l ? l.innerText : '').trim().slice(0, 40);
                if (!(g in groups)) groups[g] = [];
                if (e.checked) groups[g].push(lab);
              });
              return Object.entries(groups).map(([g, v]) => ({group: g, checked: v.join(', ') || '(NONE)'}));
            }""")
            log("=== RADIO / CHECKBOX STATE ===")
            for d in radios: log("  ", d)
            log("=== COMBOBOX SELECTIONS ===")
            for d in sel: log("  ", d)
            log("=== REQUIRED FIELDS ===")
            for d in diag: log("  ", "EMPTY!" if d['empty'] else "  ok  ", d)

        if not do_submit:
            log("NOT SUBMITTING (no --submit). Browser stays open 20s for inspection.")
            page.wait_for_timeout(20000); ctx.close(); return

        if not state["resumeChip"] or state["bad"]:
            log("NOT SUBMITTING: resume missing or invalid fields", state)
            ctx.close()
            return 2
        if hard_errors:
            log("NOT SUBMITTING: typeahead fields did not commit a value:")
            for e in hard_errors: log("   ", e)
            ctx.close()
            return 2

        # 2026-09-13 (altruist 5811204004, humaninterest 8115098): newer Greenhouse boards render
        # required "Country" and "Location (City)" widgets that the boards-api questions=true
        # schema never lists. A config built from the public schema therefore looks complete and
        # reads bad:0 -- Greenhouse only marks these invalid AFTER a submit click -- so the click
        # burns the reservation on client-side validation. Check them by id before clicking.
        # These are react-selects: once an option is committed the visible choice lives in a
        # sibling .select__single-value div and input.value goes BACK to empty, so reading
        # input.value alone false-positives on a correctly filled field. Check the committed
        # value the way the user sees it, and only fall back to input.value.
        rendered_only = page.evaluate("""() => {
          const out = [];
          for (const id of ['country', 'candidate-location']) {
            const el = document.getElementById(id);
            if (!el || el.offsetParent === null) continue;
            // 2026-09-17 (happymoney, rubrik, sayari, forter, renttherunway): five talent-pool
            // forms render a visible but OPTIONAL country combobox (aria-required="false", and
            // the label carries no "*"). Blocking on every visible-empty country turned those
            // into pre-click hard stops and cost the batch five submissions. Only a genuinely
            // required widget should stop the click.
            const lab = document.getElementById(el.getAttribute('aria-labelledby') || '');
            const starred = !!(lab && lab.textContent.includes('*'));
            if (el.getAttribute('aria-required') !== 'true' && !starred) continue;
            if ((el.value || '').trim()) continue;
            const control = el.closest('.select__control, [class*="-control"]') ||
                            el.closest('.select__value-container') || el.parentElement;
            const picked = control && control.querySelector(
              '.select__single-value, .select__multi-value__label, [class*="singleValue"]');
            if (!(picked && picked.textContent.trim())) out.push(id);
          }
          // 2026-09-17 (conga, feedzai) and (forter, upstart): three more rendered-only
          // classes that the public questions schema never lists and that Greenhouse only
          // marks invalid AFTER the click, so each one silently burned a reservation behind a
          // clean bad:0 read. Catch all three BEFORE the click instead.
          //  a) a REQUIRED consent checkbox (gdpr_processing_consent_given_1, "Please accept
          //     the terms to proceed.") that is left unticked.
          //  b) a CUSTOM EEO/demographic block with numeric ids (forter 4001712002.., jumio,
          //     samsara 498..) that the renderer marks required while the standard
          //     gender/race/veteran/disability ids are absent.
          //  c) a required question_NNN[] whose widget is a react-select rather than the
          //     checkbox fieldset the config assumed -- upstart had ONE of each on the same
          //     form, so the widget must be judged per id, not once per form.
          for (const cb of document.querySelectorAll(
                 'input[type=checkbox][required], input[type=checkbox][aria-required=true]')) {
            if (cb.offsetParent !== null && !cb.checked && !cb.name.endsWith('[]'))
              out.push(cb.id || cb.name);
          }
          for (const el of document.querySelectorAll(
                 'input[role=combobox][aria-required=true], fieldset[aria-required=true]')) {
            if (el.offsetParent === null) continue;
            const id = el.id || '';
            if (id === 'country' || id === 'candidate-location') continue;
            if (el.tagName === 'FIELDSET') {
              const boxes = el.querySelectorAll('input[type=checkbox], input[type=radio]');
              if (boxes.length && ![...boxes].some(b => b.checked)) out.push(id || '(fieldset)');
              continue;
            }
            if ((el.value || '').trim()) continue;
            const control = el.closest('.select__control, [class*="-control"]') ||
                            el.closest('.select__value-container') || el.parentElement;
            const picked = control && control.querySelector(
              '.select__single-value, .select__multi-value__label, [class*="singleValue"]');
            if (!(picked && picked.textContent.trim())) out.push(id || '(combobox)');
          }
          return out;
        }""")
        if rendered_only:
            log("NOT SUBMITTING: required rendered-only fields are empty:", rendered_only)
            log("   add country -> cfg['selects'], candidate-location -> cfg['typeaheads']")
            ctx.close()
            return 2

        # submit button: Greenhouse uses type=submit; Ashby/Lever use a plain button with "Submit" text
        cands = ([cfg["submit_selector"]] if cfg.get("submit_selector") else []) + [
            # 2026-09-18 (mashgin): Lever's real submit is #btn-submit. None of the generic
            # selectors matched a VISIBLE node, so the run fell through to the role/name
            # fallback, clicked some other "submit"-named control and sat on /apply with
            # bad:0 and no error - a silent non-confirm that still spent the reservation.
            '#btn-submit',
            'button[type=submit], #submit_app, input[type=submit]',
            'button.ashby-application-form-submit-button',
        ]
        # .first is wrong: Lever ships a hidden button[type=submit] ahead of the real one, and
        # scroll_into_view on it hangs for 30s and aborts the run (2026-09-12). Take the first
        # VISIBLE match instead of the first DOM match.
        btn = None
        for sel in cands:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 8)):
                c = loc.nth(i)
                try:
                    if c.is_visible():
                        btn = c; log(f"[submit] using selector {sel[:50]} (match {i})"); break
                except Exception:
                    continue
            if btn is not None:
                break
        if btn is None:
            role = page.get_by_role("button", name=re.compile("submit", re.I))
            for i in range(min(role.count(), 8)):
                if role.nth(i).is_visible():
                    btn = role.nth(i); log(f"[submit] using role/name fallback (match {i})"); break
        if btn is None:
            log("NOT SUBMITTING: no visible submit button found")
            ctx.close()
            return 2
        btn.scroll_into_view_if_needed(); page.wait_for_timeout(500)
        # Persist exact readback before reserving or clicking. A journal failure
        # must not consume an attempt or silently send an unrecorded answer.
        capture_qa(page, cfg, guard.ledger.parent, 'submitting', qa_session_id)
        decision = (guard.resume_email_verification(url, company, guard.ledger.parent / '_current_job_verification.json')
                    if resume_verification else guard.reserve(url, company, cfg.get('title', ''), batch))
        if decision != 'GO':
            log('NOT SUBMITTING:', decision)
            ctx.close()
            return 2
        submitted_at = time.time()
        # 2026-09-18 (mashgin, placemakr): a real Playwright click on Lever's #btn-submit left
        # the page on /apply with bad:0, no visible error and no receipt email - twice. Same
        # class as the hidden-radio bug: scroll_into_view parks the button under Lever's
        # sticky header, which swallows the mouse event. A synthetic .click() on the element
        # cannot be intercepted by anything painted over it, and it is the method the Lever
        # runbook records as working. Use it wherever the element supports it, and only fall
        # back to the real mouse click if the synthetic one leaves the page untouched.
        clicked_js = False
        try:
            btn.evaluate("e => e.click()")
            clicked_js = True
            log("[submit] clicked (synthetic)")
        except Exception as e:
            log(f"[submit] synthetic click failed ({e}); using real mouse click")
        if not clicked_js:
            btn.click()
            log("[submit] clicked")
        page.wait_for_timeout(3000)
        # 2026-09-15 (bitwarden): complete_email_code() used to run ONCE here at +3s. Boards that
        # paint the "A verification code was sent to ... / Security code" block LATER than 3s
        # skipped the OTP path entirely, never wrote NEEDS_EMAIL_CODE, and fell through to the
        # confirmation polls with 8 empty code boxes on screen. It is a cheap no-op when the
        # block is absent (it returns False on the first body read), so poll for it instead.
        code_done = complete_email_code(page, cfg, guard.ledger.parent, submitted_at)
        ok = False
        fixed_hidden_block = False
        for i in range(8):
            page.wait_for_timeout(3000)
            if not code_done:
                code_done = complete_email_code(page, cfg, guard.ledger.parent, submitted_at)
                if code_done:
                    page.wait_for_timeout(3000)
            r = page.evaluate("""() => {
                const t = document.body.innerText.toLowerCase();
                return {ok: /thank you for applying|application has been received|application submitted|successfully received/.test(t)
                            || location.pathname.includes('/confirmation')
                            // Lever's success page is <apply-url minus /apply>/thanks
                            || location.pathname.endsWith('/thanks'),
                        gone: !document.querySelector('form button[type=submit],#submit_app,input[type=submit]'),
                        bad: document.querySelectorAll('[aria-invalid="true"]').length,
                        badIds: [...document.querySelectorAll('[aria-invalid="true"]')].map(e=>e.id||e.name||'(anon)'),
                        // 2026-09-18: Lever ships its validation messages as ALWAYS-PRESENT
                        // hidden template nodes - "File exceeds the maximum upload size of
                        // 100MB" is in the DOM of every apply page from first paint. Scraping
                        // them blind reported a hard rejection on a form that had uploaded
                        // fine (parseResume returned 200). Only count VISIBLE error nodes.
                        errs: [...document.querySelectorAll('.error,[class*=error]')]
                              .filter(e => e.offsetParent !== null && e.getClientRects().length)
                              .map(e=>e.innerText.trim()).filter(t=>t&&t.length<120).slice(0,4)};
            }""")
            log(f"[check {i}]", r)
            # "gone" alone is not proof: boards whose submit button is not type=submit
            # (Ashby/Lever) make it always true. Require the success text, or gone with no errors.
            missing = any("missing entry" in e.lower() or "required" in e.lower() for e in r["errs"])
            if r["ok"]:
                ok = True; break
            # 2026-09-15 (coinbase x2, and four earlier victims): some Greenhouse boards keep a
            # REQUIRED work-experience / education block OUT of the public questions API and only
            # render it after the first submit click, so the prefill reads a clean bad:0 and the
            # reservation is burned on server-side validation. Fill that block from the same
            # verified employment history and re-click ONCE in the SAME reserved form session.
            # Field-type split matters: company/title/year are TEXT inputs but the MONTH fields
            # are react-selects, so a text .fill() on a month is only an advisory MISS.
            hidden = [b for b in r["badIds"] if re.match(
                r'(company-name|title|start-date|end-date|school|degree|discipline)--?\d', b or '')]
            if hidden and not fixed_hidden_block and cfg.get("employment"):
                capture_qa(page, cfg, guard.ledger.parent, 'observed', qa_session_id)
                fixed_hidden_block = True
                log("[hidden-block] late required block rendered:", hidden)
                emp = cfg["employment"]
                for fid, val in (("company-name-0", emp.get("company")), ("title-0", emp.get("title")),
                                 ("start-date-year-0", emp.get("start_year")),
                                 ("end-date-year-0", emp.get("end_year"))):
                    if not val:
                        continue
                    try:
                        el = page.locator(f'[id="{fid}"], [name="{fid}"]').first
                        if el.count():
                            el.fill(str(val)); log(f"[hidden-block] {fid} <- {val}")
                    except Exception as e:
                        log(f"[hidden-block] FAIL {fid}: {e}")
                for fid, val in (("start-date-month-0", emp.get("start_month")),
                                 ("end-date-month-0", emp.get("end_month"))):
                    if not val:
                        continue
                    try:
                        el = page.locator(f'[id="{fid}"], [name="{fid}"]').first
                        if not el.count():
                            log(f"[hidden-block] MISS {fid}"); continue
                        ctrl = el.locator("xpath=ancestor::*[contains(@class,'select__control')][1]")
                        (ctrl if ctrl.count() else el).click()
                        page.wait_for_timeout(500)
                        opts = page.locator('[role=option], [class*="__option"]')
                        texts = opts.all_inner_texts()
                        idx = next((k for k, t in enumerate(texts)
                                    if t.strip().lower() == str(val).lower()), None)
                        if idx is None:
                            log(f"[hidden-block] no month option {val!r} (saw {texts[:4]})"); continue
                        opts.nth(idx).click(); page.wait_for_timeout(400)
                        log(f"[hidden-block] {fid} <- {val}")
                    except Exception as e:
                        log(f"[hidden-block] FAIL {fid}: {e}")
                try:
                    btn.scroll_into_view_if_needed(); page.wait_for_timeout(400)
                    capture_qa(page, cfg, guard.ledger.parent, 'submitting', qa_session_id)
                    btn.click()
                    log("[hidden-block] re-clicked submit in the same reserved session")
                    page.wait_for_timeout(2000)
                    continue
                except Exception as e:
                    log(f"[hidden-block] re-submit FAIL: {e}")
            if missing:
                log("[submit] validation errors -> NOT submitted"); break
        page.screenshot(path=str(tmp / "after_submit.png"))
        import shutil
        proof_dir = guard.ledger.parent / '_external_evidence' / guard.day
        proof_dir.mkdir(parents=True, exist_ok=True)
        proof_path = proof_dir / f'{time.time_ns()}.png'
        shutil.copy2(tmp / 'after_submit.png', proof_path)
        guard.finish(url, confirmed=ok, evidence=page.url if ok else 'No affirmative confirmation',
                     proof=str(proof_path))
        qa_outcome(cfg, guard.ledger.parent, qa_session_id, ok,
                   page.url if ok else 'No affirmative confirmation; see ' + str(proof_path))
        pending_email = guard.ledger.parent / '_pending_email_verification.json'
        if pending_email.exists():
            previous = json.loads(pending_email.read_text())
            if previous.get('company','').casefold() == company.casefold():
                pending_email.write_text(json.dumps({'company':company,'url':url,
                    'state':'confirmed' if ok else 'unconfirmed','evidence':page.url if ok else 'No affirmative confirmation',
                    'proof':str(proof_path)},indent=2))
        log("RESULT:", "CONFIRMED" if ok else "NOT-CONFIRMED", "| url:", page.url)
        ctx.close()
        return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(main())
