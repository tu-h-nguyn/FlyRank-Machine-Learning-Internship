/*
  Contact form — the one dynamic feature on this page.

  Flow: browser  ->  fetch POST (JSON)  ->  api.web3forms.com  ->  my inbox.
  The page itself stays static (GitHub Pages can only serve files); Web3Forms is
  the rented backend that turns a POST into an email. See work/portfolio/HOW-IT-WORKS.md.
*/
(function () {
  'use strict';

  var PLACEHOLDER = 'PASTE_YOUR_WEB3FORMS_ACCESS_KEY_HERE';

  var form = document.getElementById('cf-form');
  if (!form) return;

  var statusEl = document.getElementById('cf-status');
  var submitEl = document.getElementById('cf-submit');
  var setupEl  = document.getElementById('cf-setup');
  var keyValue = (form.elements.access_key.value || '').trim();

  var configured = keyValue !== '' && keyValue !== PLACEHOLDER;
  if (!configured) setupEl.hidden = false;

  // JavaScript is available, so take over validation and use my own wording.
  form.setAttribute('novalidate', 'novalidate');

  var FIELDS = [
    { id: 'cf-name', err: 'cf-name-err', check: function (v) {
        return v ? '' : 'Please tell me your name.';
    } },
    { id: 'cf-email', err: 'cf-email-err', check: function (v) {
        if (!v) return 'I need an email address to reply to.';
        return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)
          ? '' : "That doesn't look like an email address.";
    } },
    { id: 'cf-message', err: 'cf-message-err', check: function (v) {
        if (!v) return 'Please write a message.';
        return v.length >= 10 ? '' : 'A little more detail, please (at least 10 characters).';
    } }
  ];

  function setError(field, message) {
    var input = document.getElementById(field.id);
    var errEl = document.getElementById(field.err);
    if (message) {
      errEl.textContent = message;
      errEl.hidden = false;
      input.setAttribute('aria-invalid', 'true');
    } else {
      errEl.textContent = '';
      errEl.hidden = true;
      input.removeAttribute('aria-invalid');
    }
    return !message;
  }

  function validate() {
    var firstBad = null;
    FIELDS.forEach(function (field) {
      var input = document.getElementById(field.id);
      if (!setError(field, field.check(input.value.trim())) && !firstBad) firstBad = input;
    });
    if (firstBad) firstBad.focus();
    return firstBad === null;
  }

  // Clear a field's error the moment it becomes valid again.
  FIELDS.forEach(function (field) {
    var input = document.getElementById(field.id);
    input.addEventListener('input', function () {
      if (input.getAttribute('aria-invalid') === 'true' && !field.check(input.value.trim())) {
        setError(field, '');
      }
    });
  });

  function say(message, kind) {
    statusEl.className = 'form-status' + (kind ? ' is-' + kind : '');
    statusEl.textContent = message;
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    say('', '');

    if (!configured) {
      say('This form is not connected yet — the access key is still a placeholder.', 'err');
      return;
    }
    if (!validate()) return;

    // Validation runs on the trimmed value, so the payload must be trimmed too --
    // otherwise " me@example.com" passes the check and arrives with the space
    // still on it, which breaks reply-to.
    var payload = {};
    new FormData(form).forEach(function (value, name) {
      payload[name] = (typeof value === 'string') ? value.trim() : value;
    });

    var originalLabel = submitEl.textContent;
    submitEl.disabled = true;
    submitEl.textContent = 'Sending…';
    say('Sending your message…', 'pending');

    fetch(form.action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        return res.json()
          .catch(function () { return {}; })
          .then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (result) {
        if (result.ok && result.data.success) {
          form.reset();
          say('Thanks — your message is on its way. I usually reply within a couple of days.', 'ok');
        } else {
          var why = (result.data && result.data.message)
            ? result.data.message
            : 'Something went wrong on the way out.';
          say(why + ' Please try again, or reach me on LinkedIn.', 'err');
        }
      })
      .catch(function () {
        say('Could not reach the server — check your connection and try again, or reach me on LinkedIn.', 'err');
      })
      .then(function () {
        submitEl.disabled = false;
        submitEl.textContent = originalLabel;
      });
  });
})();
