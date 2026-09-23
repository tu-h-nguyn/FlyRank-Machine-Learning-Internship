/*
  Shared behaviour for every page, inlined at build time. All of it is enhancement:
  with JavaScript off every section renders in place, the nav is plain links and the
  theme follows the system.
*/
(function () {
  'use strict';

  var root = document.documentElement;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ── Theme toggle. The initial theme is set by a tiny script in <head> before first
  //    paint; this only flips it and remembers the choice.
  var toggle = document.querySelector('.theme-toggle');
  function currentTheme() {
    var set = root.getAttribute('data-theme');
    if (set) return set;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function label() {
    if (toggle) toggle.setAttribute('aria-label', currentTheme() === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
  }
  if (toggle) {
    label();
    toggle.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* private mode: session only */ }
      label();
    });
  }

  // ── Sticky nav: a border once scrolled, and a hairline showing progress.
  var nav = document.querySelector('.nav');
  var bar = document.querySelector('.progress');
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      var y = window.pageYOffset || root.scrollTop || 0;
      var room = root.scrollHeight - window.innerHeight;
      if (nav) nav.classList.toggle('is-scrolled', y > 8);
      if (bar) bar.style.transform = 'scaleX(' + (room > 0 ? Math.min(1, y / room) : 0) + ')';
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ── Reveal on scroll.
  var targets = [].slice.call(document.querySelectorAll('.rv'));
  if (reduce || !('IntersectionObserver' in window)) {
    targets.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    targets.forEach(function (el) { io.observe(el); });
    window.addEventListener('load', function () {
      targets.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) { el.classList.add('in'); io.unobserve(el); }
      });
    });
  }

  // ── Highlight what is being read: nav on the home page, the contents list on the thesis.
  function spy(links, sections) {
    if (!links.length || !sections.length || !('IntersectionObserver' in window)) return;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var id = '#' + e.target.id;
        links.forEach(function (a) {
          var href = a.getAttribute('href') || '';
          a.classList.toggle('is-active', href === id || href.slice(-id.length - 1) === '/' + id);
        });
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    sections.forEach(function (s) { obs.observe(s); });
  }
  spy([].slice.call(document.querySelectorAll('.nav-links a[href^="#"], .menu nav a[href^="#"]')),
      [].slice.call(document.querySelectorAll('main section[id]')));
  spy([].slice.call(document.querySelectorAll('.toc a')),
      [].slice.call(document.querySelectorAll('.doc-body section[id]')));

  // ── Project filter (projects page). Cards fade before leaving the layout.
  var buttons = [].slice.call(document.querySelectorAll('.filter'));
  var cards = [].slice.call(document.querySelectorAll('article.project[data-cat]'));
  var said = document.getElementById('filter-status');
  function applyFilter(f) {
    var shown = 0;
    buttons.forEach(function (b) {
      var on = b.getAttribute('data-filter') === f;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    cards.forEach(function (c) {
      var match = f === 'all' || (' ' + c.getAttribute('data-cat') + ' ').indexOf(' ' + f + ' ') > -1;
      if (match) {
        shown++;
        c.setAttribute('data-want', '1');
        if (c.hidden) { c.hidden = false; c.classList.add('is-out'); }
        requestAnimationFrame(function () { requestAnimationFrame(function () {
          if (c.getAttribute('data-want') === '1') c.classList.remove('is-out');
        }); });
      } else {
        c.setAttribute('data-want', '0');
        c.classList.add('is-out');
        setTimeout(function () { if (c.getAttribute('data-want') === '0') c.hidden = true; }, reduce ? 0 : 300);
      }
    });
    if (said) said.textContent = f === 'all' ? 'Showing all projects' : 'Showing ' + shown + ' project' + (shown === 1 ? '' : 's');
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () { applyFilter(b.getAttribute('data-filter')); });
  });

  // ── Menu for small screens. visibility:hidden while closed keeps its links out of the tab order.
  var burger = document.querySelector('.burger');
  var menu = document.getElementById('menu');
  if (burger && menu) {
    var closeBtn = menu.querySelector('.menu-close');
    var menuLinks = [].slice.call(menu.querySelectorAll('nav a'));
    var open = function () {
      menu.classList.add('is-open'); burger.setAttribute('aria-expanded', 'true');
      document.body.classList.add('no-scroll'); setTimeout(function () { closeBtn.focus(); }, 50);
    };
    var close = function (back) {
      menu.classList.remove('is-open'); burger.setAttribute('aria-expanded', 'false');
      document.body.classList.remove('no-scroll'); if (back) burger.focus();
    };
    burger.addEventListener('click', open);
    closeBtn.addEventListener('click', function () { close(true); });
    menuLinks.forEach(function (a) { a.addEventListener('click', function () { close(false); }); });
    document.addEventListener('keydown', function (e) {
      if (!menu.classList.contains('is-open')) return;
      if (e.key === 'Escape') { close(true); return; }
      if (e.key === 'Tab') {
        var items = [closeBtn].concat(menuLinks), first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
  }

  // ── Print button (CV page).
  var printBtn = document.querySelector('[data-print]');
  if (printBtn) printBtn.addEventListener('click', function () { window.print(); });
})();
