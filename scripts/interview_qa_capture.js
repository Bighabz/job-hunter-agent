() => {
  const text = e => e ? (e.innerText || e.textContent || '').trim() : '';
  const labelled = e => (e.getAttribute('aria-labelledby') || '').split(/\s+/)
    .filter(Boolean).map(id => text(document.getElementById(id))).filter(Boolean).join('\n');
  const label = e => labelled(e) || (e.labels && [...e.labels].map(text).filter(Boolean).join('\n')) ||
    e.getAttribute('aria-label') || text(e.closest('label'));
  const container = e => e.closest('fieldset,[role=group],[role=radiogroup],[data-field-path],'
    + '[class*="field-entry"],[class*="FieldEntry"],[class*="_field"],.application-question');
  const heading = c => c && (labelled(c) || c.getAttribute('aria-label') ||
    text(c.querySelector('legend,[data-ui="field-label"],.application-label,'
      + '[class*="fieldLabel"],[class*="FieldLabel"],[class*="_label"],h2,h3,h4')));
  const rendered = e => !!(e && e.getClientRects().length &&
    getComputedStyle(e).visibility !== 'hidden' && !e.closest('[hidden],[aria-hidden="true"]'));
  const visible = e => rendered(e) || (e.labels && [...e.labels].some(rendered));
  const secret = /password|passcode|\bone[ _-]?time\b|\botp\b|verification.?code|security.?code|captcha|auth.?token|\bssn\b|social.security.(?:number|#)|bank.account|routing.number|credit.card|card.number/i;
  const rows = [], grouped = new Map();
  const elements = [...document.querySelectorAll('input,textarea,select,[contenteditable=true]')];
  for (const [index, e] of elements.entries()) {
    const type = (e.type || '').toLowerCase();
    if (['hidden', 'password', 'submit', 'button', 'reset'].includes(type) || !visible(e)) continue;
    const field = e.id || e.name || 'unlabeled-' + index;
    const c = container(e);
    const own = label(e);
    const question = (['checkbox', 'radio'].includes(type) && heading(c)) || own || heading(c) ||
      e.getAttribute('placeholder') || '[Unlabeled field: ' + field + ']';
    if (secret.test(field + ' ' + question) || e.autocomplete === 'one-time-code') continue;
    const required = !!(e.required || e.getAttribute('aria-required') === 'true');
    if (['radio', 'checkbox'].includes(type)) {
      const group = e.name || field;
      const key = type + ':' + group;
      if (!grouped.has(key)) {
        const row = {field: group, question, answer: [], options: [], required,
          label_source: heading(c) ? 'group heading' : 'control label', answer_state: 'unanswered'};
        grouped.set(key, row); rows.push(row);
      }
      const row = grouped.get(key), option = own || e.value;
      row.options.push(option); row.required ||= required;
      if (e.checked) { row.answer.push(option); row.answer_state = 'selected'; }
      continue;
    }
    let answer = e.isContentEditable ? text(e) : e.value || '';
    let options;
    if (e.tagName === 'SELECT') {
      answer = [...e.selectedOptions].filter(o => o.value !== '').map(text);
      options = [...e.options].map(text);
    } else if (type === 'file') {
      answer = [...e.files].map(f => f.name);
    } else if (e.getAttribute('role') === 'combobox') {
      const control = e.closest('.select__control,[class*="-control"]') || e.parentElement;
      const chosen = [...control.querySelectorAll('.select__single-value,.select__multi-value__label,'
        + '[class*="singleValue"],[class*="multiValueLabel"]')].map(text).filter(Boolean);
      // A typed search term is not proof that a choice was committed.
      if (chosen.length) answer = chosen;
      else if (control.matches('.select__control,[class*="-control"]')) answer = [];
    }
    rows.push({field, question, answer, ...(options ? {options} : {}), required,
      label_source: own ? 'control label' : heading(c) ? 'group heading' : 'fallback',
      answer_state: answer && answer.length ? 'observed_value' : 'unanswered'});
  }
  // Ashby-style Yes/No buttons are not inputs and need an explicit capture path.
  for (const c of document.querySelectorAll('[data-field-path],[role=group],[role=radiogroup]')) {
    const buttons = [...c.querySelectorAll('button[data-option],button[aria-pressed],[role=radio]')]
      .filter(rendered);
    if (!buttons.length) continue;
    const field = c.getAttribute('data-field-path') || c.id || 'button-group-' + rows.length;
    const question = heading(c) || text(c.querySelector('label')) || '[Unlabeled group: ' + field + ']';
    if (secret.test(field + ' ' + question)) continue;
    const selected = buttons.filter(b => b.getAttribute('aria-pressed') === 'true' ||
      b.getAttribute('aria-checked') === 'true').map(text);
    rows.push({field, question, answer: selected, options: buttons.map(text),
      answer_state: selected.length ? 'selected' : 'unanswered', label_source: 'button group heading'});
  }
  return rows;
}
