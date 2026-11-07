/* Deploy Guide export — PDF (via the browser's print dialog) and Markdown.
 *
 * Shared by the AWS, GCP and Azure pages. Those pages are standalone as Jinja
 * templates — none extends or includes another — but they already share
 * app.css, and this is page chrome rather than cloud logic, so it lives once.
 *
 * Both exporters read the rendered #guide-body rather than the step objects
 * buildDeployGuide() returns. The CloudFormation branch of showDeployGuide()
 * writes its markup straight into the panel and never builds those objects, so
 * the DOM is the only place both variants meet.
 */
(function () {
  'use strict';

  function guideBody() {
    var el = document.getElementById('guide-body');
    if (!el || !el.innerHTML.trim()) return null;
    return el;
  }

  function guideSub() {
    var el = document.getElementById('guide-sub');
    return el ? el.textContent.trim() : '';
  }

  /** "acme · aws" -> "acme-aws-deploy-guide". Falls back to the page path. */
  function baseName() {
    var cust = '';
    if (typeof getCustName === 'function') {
      try { cust = getCustName(); } catch (e) { cust = ''; }
    }
    var cloud = (location.pathname.replace(/\//g, '') || 'terraform');
    var parts = [cust, cloud, 'deploy-guide'].filter(Boolean).join('-');
    return parts.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/-+/g, '-');
  }

  function heading() {
    var cust = '';
    if (typeof getCustName === 'function') {
      try { cust = getCustName(); } catch (e) { cust = ''; }
    }
    return (cust ? cust + ' — ' : '') + 'Deploy Guide';
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function noGuide() {
    alert('Open the Deploy Guide first — there is nothing to export yet.');
  }

  // ── PDF ────────────────────────────────────────────────────────────────────
  // A self-contained document in a new window, not window.print() on the app.
  // The app is a fixed-height flex layout with overflow:hidden panels, so
  // printing it directly clips the guide to whatever is on screen.

  var PRINT_CSS = [
    '@page { margin: 16mm 14mm; }',
    'body { font: 11pt/1.5 Georgia, "Times New Roman", serif; color: #1a1a1a;',
    '       margin: 0; padding: 0; }',
    'h1 { font: 700 20pt/1.2 Helvetica, Arial, sans-serif; margin: 0 0 4pt; }',
    '.sub { font: 10pt/1.4 Helvetica, Arial, sans-serif; color: #555;',
    '       margin: 0 0 4pt; }',
    '.meta { font: 9pt/1.4 Helvetica, Arial, sans-serif; color: #888;',
    '        border-bottom: 1.5pt solid #333; padding-bottom: 10pt;',
    '        margin-bottom: 16pt; }',
    // Keep a step and its commands on one page wherever the page break allows.
    '.dg-step { break-inside: avoid; page-break-inside: avoid;',
    '           border-bottom: 0.5pt solid #ddd; padding: 0 0 12pt; margin: 0 0 12pt; }',
    '.dg-step:last-child { border-bottom: none; }',
    '.dg-step-head { display: flex; align-items: baseline; gap: 8pt;',
    '                margin-bottom: 5pt; }',
    '.dg-step-num { font: 700 9pt Helvetica, Arial, sans-serif; color: #fff;',
    '               background: #1a1a1a; border-radius: 50%; width: 16pt;',
    '               height: 16pt; min-width: 16pt; display: inline-flex;',
    '               align-items: center; justify-content: center; }',
    '.dg-step-title { font: 700 12pt Helvetica, Arial, sans-serif; flex: 1; }',
    '.dg-step-time { font: 9pt Helvetica, Arial, sans-serif; color: #666;',
    '                white-space: nowrap; }',
    '.dg-step-desc { margin-bottom: 7pt; }',
    '.dg-init-note { font-style: italic; color: #555; margin-bottom: 14pt; }',
    '.dg-cmd, .dg-res-cfg-item, .dg-ref-row, code {',
    '  font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 9.5pt; }',
    '.dg-cmd { background: #f4f4f2; border: 0.5pt solid #ddd; border-radius: 3pt;',
    '          padding: 5pt 8pt; margin-bottom: 3pt; white-space: pre-wrap;',
    '          word-break: break-all; }',
    '.dg-prompt { color: #888; margin-right: 6pt; }',
    '.dg-warn, .dg-tip { border-left: 2.5pt solid #999; padding: 4pt 0 4pt 8pt;',
    '                    margin-bottom: 7pt; font-size: 10pt; }',
    '.dg-warn { border-left-color: #c0392b; }',
    '.dg-resource { border: 0.5pt solid #ddd; border-radius: 3pt; padding: 8pt;',
    '               margin-top: 8pt; break-inside: avoid; page-break-inside: avoid; }',
    '.dg-res-name { font: 700 10pt Helvetica, Arial, sans-serif; margin-bottom: 5pt; }',
    '.dg-refs-label { font: 700 8.5pt Helvetica, Arial, sans-serif;',
    '                 text-transform: uppercase; letter-spacing: 0.05em;',
    '                 color: #777; margin: 7pt 0 3pt; }',
    '.dg-ref-row { margin-bottom: 2pt; }',
    '.dg-ref-arrow { color: #888; padding: 0 4pt; }',
    '.dg-empty { color: #888; font-style: italic; }'
  ].join('\n');

  function exportGuidePdf() {
    var body = guideBody();
    if (!body) { noGuide(); return; }

    var doc = '<!doctype html><html><head><meta charset="utf-8">' +
      '<title>' + escapeHtml(baseName()) + '</title>' +
      '<style>' + PRINT_CSS + '</style></head><body>' +
      '<h1>' + escapeHtml(heading()) + '</h1>' +
      '<div class="sub">' + escapeHtml(guideSub()) + '</div>' +
      '<div class="meta">Generated by Terraflow Studio · ' + today() + '</div>' +
      body.innerHTML +
      '</body></html>';

    var w = window.open('', '_blank');
    if (!w) {
      alert('Allow pop-ups for this site to export the guide as PDF, ' +
            'or use the .md export instead.');
      return;
    }
    w.document.open();
    w.document.write(doc);
    w.document.close();
    // Let the new document lay out before the print dialog measures it.
    w.onload = function () { w.focus(); w.print(); };
    setTimeout(function () { if (!w.closed) { w.focus(); w.print(); } }, 400);
  }

  // ── Markdown ───────────────────────────────────────────────────────────────

  function text(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  /** Like text(), but keeps adjacent spans apart: the reference rows put the
   *  variable, the arrow and the source in touching elements, so plain
   *  textContent runs them together as "odb_network_id→used by peerings". */
  function spacedText(el) {
    var parts = [];
    Array.prototype.forEach.call(el.childNodes, function (n) {
      var t = (n.textContent || '').replace(/\s+/g, ' ').trim();
      if (t) parts.push(t);
    });
    return parts.length ? parts.join(' ') : text(el);
  }

  function stepMarkdown(step, n) {
    var out = [];
    var title = step.querySelector('.dg-step-title');
    var time = step.querySelector('.dg-step-time');
    out.push('## ' + n + '. ' + (title ? text(title) : 'Step ' + n) +
             (time ? '  \n_' + text(time) + '_' : ''));
    out.push('');

    var desc = step.querySelector('.dg-step-desc');
    if (desc && text(desc)) { out.push(text(desc)); out.push(''); }

    ['.dg-warn', '.dg-tip'].forEach(function (sel) {
      var el = step.querySelector(sel);
      if (el && text(el)) { out.push('> ' + text(el)); out.push(''); }
    });

    var cmds = step.querySelectorAll('.dg-cmd');
    if (cmds.length) {
      out.push('```bash');
      Array.prototype.forEach.call(cmds, function (c) {
        var prompt = c.querySelector('.dg-prompt');
        var line = text(c);
        if (prompt) line = line.slice(text(prompt).length).trim();
        out.push(line);
      });
      out.push('```');
      out.push('');
    }

    Array.prototype.forEach.call(step.querySelectorAll('.dg-resource'), function (r) {
      var name = r.querySelector('.dg-res-name');
      if (name) { out.push('**' + text(name) + '**'); out.push(''); }
      Array.prototype.forEach.call(r.querySelectorAll('.dg-res-cfg-item'), function (c) {
        out.push('- ' + text(c));
      });
      var label = null;
      Array.prototype.forEach.call(r.children, function (child) {
        if (child.classList.contains('dg-refs-label')) {
          label = text(child);
          out.push('');
          out.push('_' + label + '_');
          out.push('');
        } else if (child.classList.contains('dg-ref-row')) {
          out.push('- `' + spacedText(child) + '`');
        }
      });
      out.push('');
    });

    return out.join('\n');
  }

  function exportGuideMarkdown() {
    var body = guideBody();
    if (!body) { noGuide(); return; }

    var out = ['# ' + heading(), ''];
    if (guideSub()) { out.push('`' + guideSub() + '`'); out.push(''); }
    out.push('Generated by Terraflow Studio · ' + today());
    out.push('');

    var note = body.querySelector('.dg-init-note');
    if (note) { out.push('> ' + text(note)); out.push(''); }

    var steps = body.querySelectorAll('.dg-step');
    if (!steps.length) {
      out.push(text(body) || '_No deployment steps yet._');
    } else {
      Array.prototype.forEach.call(steps, function (step, i) {
        out.push('---');
        out.push('');
        out.push(stepMarkdown(step, i + 1));
      });
    }

    download(baseName() + '.md', out.join('\n').replace(/\n{3,}/g, '\n\n'));
  }

  // ── Plumbing ───────────────────────────────────────────────────────────────

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function download(name, body) {
    var blob = new Blob([body], { type: 'text/markdown;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  window.exportGuidePdf = exportGuidePdf;
  window.exportGuideMarkdown = exportGuideMarkdown;
})();
