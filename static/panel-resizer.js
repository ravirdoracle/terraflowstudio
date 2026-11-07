/* Draggable divider between the form and the output panel, shared by every page.
 *
 * The width is kept in localStorage under one key for all pages, so dragging it
 * on one page carries to the rest. It was copied into each page; the Data Guard
 * and OCI DB copies saved parseInt() of a CSS variable that is unset until the
 * divider is first dragged, so a plain click stored "NaN". The next load set
 * --rhs-width to "NaNpx", which invalidates the page's whole grid: the output
 * panel dropped below the form, on every page. So: only a dragged, finite width
 * is ever stored, and a stored value that is not one is discarded on load -
 * which also repairs browsers that already hold "NaN".
 */
(function () {
  'use strict';
  var KEY = 'tf-rhs-width', MIN = 280, MAX_FRAC = 0.82, DEFAULT = 500;

  function maxWidth() { return window.innerWidth * MAX_FRAC; }
  function clamp(w) { return Math.max(MIN, Math.min(maxWidth(), w)); }
  function load() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function save(w) { try { localStorage.setItem(KEY, String(Math.round(w))); } catch (e) { /* storage blocked */ } }
  function forget() { try { localStorage.removeItem(KEY); } catch (e) { /* storage blocked */ } }

  function init() {
    var app = document.querySelector('.app');
    var rz = document.getElementById('panel-resizer');
    if (!app || !rz) return;

    var saved = load();
    if (saved !== null) {
      var w = parseFloat(saved);
      // A window narrower than when it was saved only clamps the width; a value
      // that is not a usable width at all is dropped so the CSS default applies.
      if (isFinite(w) && w >= MIN) app.style.setProperty('--rhs-width', clamp(w) + 'px');
      else forget();
    }

    function current() {
      var v = parseFloat(getComputedStyle(app).getPropertyValue('--rhs-width'));
      return isFinite(v) ? v : DEFAULT;   // unset until the first drag
    }

    var startX = 0, startW = DEFAULT, moved = false;
    function onMove(e) {
      moved = true;
      app.style.setProperty('--rhs-width', clamp(startW + (startX - e.clientX)) + 'px');
    }
    function onUp() {
      rz.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (moved) save(current());      // a click without a drag changes nothing
    }
    rz.addEventListener('mousedown', function (e) {
      e.preventDefault();
      startX = e.clientX;
      startW = current();
      moved = false;
      rz.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
