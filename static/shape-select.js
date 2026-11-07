/* Exadata shape dropdowns, shared by the AWS, Azure and GCP product pages.
 *
 * The shape list, the database/storage server models offered for each shape and
 * the default shape all come from config/<cloud>_shapes.json, injected into each
 * page by its route and edited at /regions. These helpers only render it — they
 * hold no shape values of their own, which is the whole point: the three pages
 * used to carry three hand-maintained <option> lists that had already drifted
 * apart (AWS and GCP offered X10M, Azure did not).
 *
 * Every function takes the page's own catalogue array as its first argument, so
 * nothing here knows which cloud it is running on.
 */

/** The entry for one shape, or undefined. */
function shapeEntry(catalogue, shape) {
  return (catalogue || []).find(s => s.shape === shape);
}

/** Live shapes first, planned ones greyed and suffixed, like the region select. */
function shapeOptionsHTML(catalogue, selected) {
  const live = (catalogue || []).filter(s => s.status === 'live');
  const planned = (catalogue || []).filter(s => s.status === 'planned');
  const opt = s =>
    `<option value="${s.shape}"${s.shape === selected ? ' selected' : ''}` +
    `${s.status === 'planned' ? ' style="color:var(--ink3)"' : ''}>` +
    `${s.label || s.shape}${s.status === 'planned' ? ' — planned' : ''}</option>`;
  // A saved config may name a shape the catalogue no longer lists. Keep it
  // rather than silently switching the card to something else.
  let extra = '';
  if (selected && !shapeEntry(catalogue, selected)) {
    extra = `<option value="${selected}" selected>${selected} (not in catalogue)</option>`;
  }
  return extra + live.map(opt).join('') + planned.map(opt).join('');
}

function shapeSelectHTML(catalogue, id, selected, onchange) {
  return `<select id="${id}" onchange="${onchange}">${shapeOptionsHTML(catalogue, selected)}</select>`;
}

/** Server models offered for a shape. kind is 'database' or 'storage'. */
function serverTypesFor(catalogue, shape, kind) {
  const entry = shapeEntry(catalogue, shape);
  if (!entry) return [];
  return entry[kind === 'database' ? 'database_server_types' : 'storage_server_types'] || [];
}

/** True when the provider rejects the infrastructure without both server types. */
function shapeRequiresServerTypes(catalogue, shape) {
  const entry = shapeEntry(catalogue, shape);
  return !!(entry && entry.server_types_required);
}

/** The only model offered for a shape, or '' when there is a choice to make. */
function soleServerType(catalogue, shape, kind) {
  const types = serverTypesFor(catalogue, shape, kind);
  return types.length === 1 ? types[0] : '';
}

/**
 * Keep an infra's stored server types consistent with its shape.
 *
 * Called from the card's read function, so the state array and the dropdown
 * never disagree — a value carried over from a different shape would otherwise
 * sit in the payload while the card showed something else. Where a required
 * shape offers exactly one model there is nothing to choose, so it is filled in;
 * where it offers several (storage is HC or EF) the choice is left to the user
 * and the validator asks for it.
 */
function normaliseServerTypes(catalogue, entry) {
  const shape = entry.shape;
  ['database', 'storage'].forEach(kind => {
    const key = kind === 'database' ? 'database_server_type' : 'storage_server_type';
    const types = serverTypesFor(catalogue, shape, kind);
    // A model that belongs to another shape is not merely wrong, it would be
    // rejected at apply. Drop it rather than carrying it forward.
    if (entry[key] && types.length && !types.includes(entry[key])) entry[key] = '';
    if (!entry[key] && shapeRequiresServerTypes(catalogue, shape)) {
      entry[key] = soleServerType(catalogue, shape, kind);
    }
  });
  return entry;
}

/**
 * A server-type dropdown for the selected shape.
 *
 * Blank means "let the provider choose", which is only offered when the shape
 * does not require a value. For a shape that does, the blank option says so and
 * the payload validator rejects it. A stored value the catalogue does not list
 * is preserved and marked, so opening an older config never quietly rewrites it.
 */
function serverTypeSelectHTML(catalogue, id, shape, kind, selected, onchange) {
  const types = serverTypesFor(catalogue, shape, kind);
  const required = shapeRequiresServerTypes(catalogue, shape);
  const blankLabel = required ? '— select —' : '— provider default —';
  let opts = `<option value=""${selected ? '' : ' selected'}>${blankLabel}</option>`;
  if (selected && !types.includes(selected)) {
    opts += `<option value="${selected}" selected>${selected} (not in catalogue)</option>`;
  }
  opts += types.map(t =>
    `<option value="${t}"${t === selected ? ' selected' : ''}>${t}</option>`).join('');
  if (!types.length) {
    opts += `<option value="" disabled style="color:var(--ink3)">No models listed for ${shape || 'this shape'}</option>`;
  }
  return `<select id="${id}" onchange="${onchange}">${opts}</select>`;
}
