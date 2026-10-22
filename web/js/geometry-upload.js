import {createViewer} from './viewer3d.js?v=geometry-3';

const node = (tag, text) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
};

// One cached import keeps original buffers available until Save draft attaches
// them to the project. Later visits fetch the authenticated retained originals.
export function mountGeometry({read, write, api, source, action, save}) {
  const $ = id => document.getElementById(id);
  let enabled = false, attached = false, ready = false, dirty = false;
  let viewer = null, cache = null, shown = '', selected = '', loading = '', request = 0;

  function controls() {
    $('geometry-files').disabled = !enabled;
    $('geometry-units').disabled = !enabled;
    $('geometry-upload').disabled = !enabled || !$('geometry-files').files.length || !$('geometry-units').value;
    $('geometry-reset').disabled = !enabled || !ready;
    $('geometry-remove').disabled = !enabled || !attached;
    $('geometry-save').disabled = !enabled || !dirty;
  }
  function status(text, error = false) {
    $('geometry-status').textContent = text;
    $('geometry-status').className = error ? 'error' : '';
  }
  function empty(text) {
    ready = false; shown = '';
    viewer?.clear();
    $('geometry-empty').hidden = false;
    $('geometry-empty').textContent = text;
    $('geometry-record').replaceChildren();
    controls();
  }
  function show(report, buffers, key) {
    const list = node('ul');
    report.components.forEach(component => {
      const item = node('li');
      item.append(node('strong', component.filename), node('span', ` · ${component.triangle_count.toLocaleString()} triangles`));
      list.append(item);
    });
    const extent = report.bounding_box_m.max.map((v, i) => v - report.bounding_box_m.min[i]);
    const dimensions = extent.map(v => Number(v.toPrecision(5))).join(' × ');
    const details = node('details');
    details.append(node('summary', 'Geometry import record'), node('pre', JSON.stringify(report, null, 2)));
    $('geometry-record').replaceChildren(list,
      node('p', `Source units: ${({m:'metres',mm:'millimetres',cm:'centimetres',in:'inches',ft:'feet'})[report.conversion.from]}. Preview bounds: ${dimensions} m.`),
      node('p', `${report.shell_count} ${report.shell_count === 1 ? 'shell' : 'shells'} · ${report.topology_issues.length} topology issue groups.`), details);
    try {
      viewer ??= createViewer($('geometry-view'));
      viewer.showStl(buffers, report.unit_scale_to_m, report.transform);
      $('geometry-empty').hidden = true;
      ready = true; shown = key;
    } catch (error) {
      ready = false; shown = key;
      $('geometry-empty').hidden = false;
      $('geometry-empty').textContent = '3D preview unavailable: ' + error.message;
    }
    controls();
  }

  async function sync(project, snapshot, isDirty) {
    dirty = isDirty;
    const digest = snapshot?.assembly?.geometry_import_sha256;
    const key = project ? project.project_id + ':' + (digest || '') : '';
    attached = Boolean(digest || snapshot?.assembly?.geometry_revision_sha256 || snapshot?.assembly?.components?.length);
    if (selected !== key) {
      ++request; loading = '';
      $('geometry-files').value = ''; $('geometry-units').value = '';
    }
    selected = key;
    controls();
    if (digest && shown === key) {
      status(dirty ? 'Geometry attached to this draft. Save draft to retain your changes.' : 'Geometry saved with this project.');
      return;
    }
    if (digest && loading === key) return;
    const pending = ++request;
    if (!digest) {
      if (!project) cache = null;
      const savedAssembly = project ? JSON.parse(project.snapshot_json).assembly : null;
      const removed = !attached && Boolean(savedAssembly?.geometry_import_sha256 || savedAssembly?.geometry_revision_sha256 || savedAssembly?.components?.length);
      empty(attached ? 'No saved STL preview record.' : 'No STL attached.');
      status(!project ? 'Create or open a project to attach geometry.' : attached
        ? 'This older design has geometry references without a preview record. Upload the STL to replace them.'
        : dirty && removed ? 'Geometry removed from the draft. Save draft to retain this change.' : 'Choose an STL and its source units to begin.');
      return;
    }
    loading = key;
    empty('Loading retained STL geometry…');
    status('Loading original STL files from this project…');
    try {
      let loaded = cache;
      if (loaded?.report.report_sha256 !== digest) {
        const {report} = await api(`/projects/${project.project_id}/geometry`);
        if (report?.report_sha256 !== digest) throw new Error('Save the changed geometry reference before reopening its preview.');
        const buffers = await Promise.all(report.components.map(component =>
          source(`/projects/${project.project_id}/geometry/${component.source_sha256}.stl`)));
        loaded = {report, buffers};
      }
      if (pending !== request || selected !== key) return;
      cache = loaded; loading = '';
      show(loaded.report, loaded.buffers, key);
      status(!ready ? 'STL attached, but the 3D preview is unavailable in this browser. Save draft to retain your changes.'
        : dirty ? 'STL uploaded and previewed. Save draft to keep it with this project.' : 'Geometry saved with this project.');
    } catch (error) {
      if (pending !== request || selected !== key) return;
      loading = '';
      empty('Saved geometry could not be loaded.');
      status(error.message, true);
    }
  }

  $('geometry-files').addEventListener('change', controls);
  $('geometry-units').addEventListener('change', controls);
  $('geometry-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!enabled) return;
    action(async () => {
      try {
        const files = [...$('geometry-files').files], units = $('geometry-units').value;
        if (!files.length || !units) throw new Error('Choose STL files and declare their source units.');
        if (files.some(file => !file.name.toLowerCase().endsWith('.stl'))) throw new Error('Choose STL files only.');
        if (files.reduce((total, file) => total + file.size, 0) > 50_000_000) throw new Error('Selected STL files exceed the 50 MB total limit.');
        // Parse draft JSON before retaining files so malformed edits are preserved.
        const snapshot = read();
        const mapping = value => value && typeof value === 'object' && !Array.isArray(value);
        if (!mapping(snapshot.assembly) || !mapping(snapshot.units_and_frames)) throw new Error('Restore valid assembly and units groups before uploading geometry.');
        status('Uploading STL and checking geometry…');
        const body = new FormData(); body.append('source_units', units);
        files.forEach(file => body.append('files', file));
        const report = await api('/import', {method: 'POST', body});
        const buffers = await Promise.all(files.map(file => file.arrayBuffer()));
        cache = {report, buffers};
        snapshot.assembly.geometry_import_sha256 = report.report_sha256;
        snapshot.assembly.geometry_revision_sha256 = report.geometry_revision_sha256;
        snapshot.assembly.components = report.components;
        snapshot.units_and_frames.source_units = report.conversion.from;
        snapshot.units_and_frames.cad_transform = Object.fromEntries(
          ['scale', 'rotation_deg_zyx', 'translation_m'].map(key => [key, report.transform[key]]));
        write(snapshot);
      } catch (error) {
        status('Upload failed. ' + error.message + ' Current geometry was kept.', true);
        throw error;
      }
    });
  });
  $('geometry-remove').addEventListener('click', () => {
    if (!enabled || !attached) return;
    try {
      const snapshot = read();
      snapshot.assembly.geometry_import_sha256 = null;
      snapshot.assembly.geometry_revision_sha256 = null;
      snapshot.assembly.components = [];
      snapshot.units_and_frames.source_units = null;
      snapshot.units_and_frames.cad_transform = {scale: 1, rotation_deg_zyx: [0, 0, 0], translation_m: [0, 0, 0]};
      cache = null;
      write(snapshot);
    } catch (error) { status(error.message, true); }
  });
  $('geometry-reset').addEventListener('click', () => viewer?.reset());
  $('geometry-save').addEventListener('click', save);
  return {sync, setEnabled(value, isDirty) { enabled = value; dirty = isDirty; controls(); }};
}
