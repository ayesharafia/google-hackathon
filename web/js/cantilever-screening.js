function validCantilever(data, req) {
  try {
    const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
    const own = (x, k) => Object.prototype.hasOwnProperty.call(x, k);
    const exact = (x, keys) => object(x) && Object.keys(x).length === keys.length && keys.every(k => own(x, k));
    const equal = (a, b) => {
      if (typeof a !== typeof b) return false;
      if (a === null || b === null || typeof a !== 'object')
        return typeof a === 'number' ? Number.isFinite(a) && a === b : a === b;
      if (Array.isArray(a) !== Array.isArray(b)) return false;
      if (Array.isArray(a) && a.length !== b.length) return false;
      const keys = Object.keys(a);
      return keys.length === Object.keys(b).length && keys.every(k => own(b, k) && equal(a[k], b[k]));
    };
    const numbers = ['length_m', 'width_m', 'depth_m', 'youngs_modulus_pa', 'tip_load_n', 'uniform_load_n_m', 'declared_min_slenderness', 'declared_max_deflection_ratio', 'declared_max_slope_rad'];
    const fields = ['evaluation', 'property_source', 'applicability_declaration', ...numbers];
    if (!object(data) || !exact(req, fields)) return false;
    if (req.evaluation !== 'rectangular_cantilever_screening') return false;
    if (!['property_source', 'applicability_declaration'].every(k => typeof req[k] === 'string' && req[k].trim().length > 0 && Array.from(req[k]).length <= 2000)) return false;
    if (!numbers.every(k => typeof req[k] === 'number' && Number.isFinite(req[k]) && (k === 'tip_load_n' || k === 'uniform_load_n_m' ? req[k] >= 0 : req[k] > 0))) return false;
    if (data.model_id !== 'rectangular_cantilever_linear_screening_v1' || data.status !== 'SCREENING_COMPUTED' || data.schema_version !== 'cantilever_screening_request_v1' || data.evidence_level !== 'unverified' || data.aircraft_status !== null || data.feasibility !== null) return false;
    if (!equal(data.inputs, req)) return false;
    if (!['input_sha256', 'evaluation_sha256'].every(k => typeof data[k] === 'string' && data[k].length === 64 && /^[0-9a-fA-F]{64}$/.test(data[k]))) return false;
    const units = {
      second_moment_m4: 'm^4',
      flexural_rigidity_n_m2: 'N*m^2',
      root_shear_magnitude_n: 'N',
      root_moment_magnitude_n_m: 'N*m',
      tip_deflection_m: 'm',
      tip_slope_rad: 'rad',
      root_outer_fiber_stress_magnitude_pa: 'Pa',
      slenderness: '1',
      deflection_ratio: '1'
    };
    const keys = Object.keys(units);
    const positive = ['second_moment_m4', 'flexural_rigidity_n_m2', 'slenderness'];
    return exact(data.outputs, keys) && exact(data.output_units, keys) && keys.every(k => data.output_units[k] === units[k] && typeof data.outputs[k] === 'number' && Number.isFinite(data.outputs[k]) && (positive.includes(k) ? data.outputs[k] > 0 : data.outputs[k] >= 0));
  } catch (_) {
    return false;
  }
}
export function mountCantilever(root,{api,readContext,isContext}) {
  const doc=root.ownerDocument;
  const node=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const test=(e,key)=>{e.dataset.testid='cantilever-'+key;return e;};
  const fields=[['length_m','Beam length (m)'],['width_m','Rectangular width (m)'],['depth_m','Bending depth (m)'],['youngs_modulus_pa',"Young's modulus (Pa)"],['tip_load_n','End transverse load magnitude (N)'],['uniform_load_n_m','Uniform transverse load magnitude (N/m)'],['declared_min_slenderness','Declared minimum length / bending depth'],['declared_max_deflection_ratio','Declared maximum tip deflection / length'],['declared_max_slope_rad','Declared maximum tip slope (rad)']];
  const section=node('section',undefined,'cantilever-screening');
  section.append(node('h2','Ideal rectangular cantilever screening'),node('p','Independent of aircraft configuration and saved projects. Both loads act in one positive transverse direction. The fixed root opposes the applied force and moment; reaction and stress outputs are magnitudes.'));
  section.append(node('p','Euler-Bernoulli slender prismatic beam, ideal fixed root, constant isotropic linear elasticity and small rotation are assumed. Sources and limits are caller declarations, not verified applicability. No shear deformation, torsion, buckling, fatigue, joints, aeroelasticity, yield, safety, aircraft strength, FEM or experimental validation. Binary64 numerical limits can cause refusal.','cantilever-warning'));
  const form=node('form'),grid=node('div',undefined,'cantilever-grid'),inputs=new Map(),texts=new Map();form.noValidate=true;
  for(const [key,label] of fields){const wrap=node('label'),e=test(node('input'),key);e.type='number';e.step='any';e.required=true;wrap.append(node('span',label),e);grid.append(wrap);inputs.set(key,e);}
  form.append(grid);
  for(const [key,label] of [['property_source','Material property and load source declaration'],['applicability_declaration','Why the beam idealization and declared limits fit this case']]){const wrap=node('label'),e=test(node('textarea'),key);e.rows=3;e.required=true;wrap.append(node('span',label+' (1 to 2000 characters)'),e);form.append(wrap);texts.set(key,e);}
  const run=test(node('button','Run cantilever screening'),'run');run.type='submit';run.disabled=true;
  const status=test(node('p','Enter all nine numeric values and both declarations.'),'status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const result=test(node('div',undefined,'cantilever-result'),'result');result.hidden=true;form.append(run);section.append(form,status,result);root.append(section);
  let serial=0,busy=false,ctx=readContext();
  function request(){const req={evaluation:'rectangular_cantilever_screening'};for(const [key,e] of inputs){if(!e.value.trim()||e.validity.badInput)return null;const value=Number(e.value);if(!Number.isFinite(value)||(key==='tip_load_n'||key==='uniform_load_n_m'?value<0:value<=0))return null;req[key]=value;}for(const [key,e] of texts){if(!e.value.trim()||Array.from(e.value).length>2000)return null;req[key]=e.value;}return req;}
  function clear(){result.replaceChildren();result.hidden=true;}
  function refresh(){run.disabled=busy||!request();}
  function syncContext(){if(isContext(ctx))return false;ctx=readContext();++serial;busy=false;inputs.forEach(e=>e.value='');texts.forEach(e=>e.value='');clear();refresh();status.textContent='Connection changed. Re-enter inputs after connecting.';return true;}
  function current(id,snapshot){if(!isContext(snapshot)){syncContext();return false;}return id===serial;}
  form.addEventListener('input',()=>{syncContext();++serial;busy=false;clear();refresh();status.textContent=request()?'Ready for ideal cantilever screening.':'Enter all required values within the declared ranges.';});
  const labels={second_moment_m4:'Centroidal second moment (m^4)',flexural_rigidity_n_m2:'Flexural rigidity EI (N*m^2)',root_shear_magnitude_n:'Root shear magnitude (N)',root_moment_magnitude_n_m:'Root bending moment magnitude (N*m)',tip_deflection_m:'Tip deflection in load direction (m)',tip_slope_rad:'Tip deflection derivative / small-rotation slope (rad)',root_outer_fiber_stress_magnitude_pa:'Root outer-fiber bending stress magnitude (Pa)',slenderness:'Length / bending depth',deflection_ratio:'Tip deflection / length'};
  function render(data,req){const list=node('dl');for(const [key,label] of Object.entries(labels))list.append(node('dt',label),node('dd',String(data.outputs[key])));result.append(list,node('p','SCREENING_COMPUTED. Evidence unverified. No aircraft status or feasibility verdict.'),node('p','Property and load source declaration: '+req.property_source),node('p','Applicability declaration: '+req.applicability_declaration),node('p','Caller-declared limits: minimum slenderness '+req.declared_min_slenderness+', maximum deflection ratio '+req.declared_max_deflection_ratio+', maximum slope '+req.declared_max_slope_rad+' rad. Passing these limits is not engineering acceptance or physical validation.'));const hashes=node('dl');hashes.append(node('dt','Input SHA-256'),node('dd',data.input_sha256),node('dt','Evaluation SHA-256'),node('dd',data.evaluation_sha256));result.append(hashes,node('p','Response shape, units, finite values, input echo and hash format checked. No independent equation, numerical or authenticity verification is performed here.'));result.hidden=false;}
  form.addEventListener('submit',async event=>{event.preventDefault();if(syncContext()||busy)return;const req=request();if(!req)return;const snapshot=readContext(),id=++serial;busy=true;clear();refresh();status.textContent='Computing ideal cantilever screening...';try{const response=await api('/cantilever/screen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});if(!current(id,snapshot))return;const data=response&&typeof response.json==='function'?await response.json():response;if(!current(id,snapshot))return;if(data?.status==='MODEL_INAPPLICABLE'||data?.status==='SOLVER_UNSUPPORTED'){status.textContent=data.status+': '+(Array.isArray(data.reasons)?data.reasons.filter(v=>typeof v==='string').join('; '):'Check idealization, declared limits and supported numerical range.');return;}if(response?.ok===false||!validCantilever(data,req))throw new Error('Invalid response');render(data,req);status.textContent='SCREENING_COMPUTED - unverified ideal cantilever screening.';}catch{if(current(id,snapshot)){clear();status.textContent='Cantilever screening failed. Check connection and inputs.';}}finally{if(current(id,snapshot)){busy=false;refresh();}}});
  return {syncContext};
}
