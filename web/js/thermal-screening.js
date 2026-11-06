function validThermal(data, req) {
  try {
    const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
    const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
    const keys = (v, ks) => object(v) && Object.keys(v).length === ks.length && ks.every(k => own(v, k));
    const exact = (a, b) => {
      if (a === b) return true;
      if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
      if (Array.isArray(a) !== Array.isArray(b)) return false;
      if (Array.isArray(a) && a.length !== b.length) return false;
      const ak = Object.keys(a), bk = Object.keys(b);
      return ak.length === bk.length && ak.every(k => own(b, k) && exact(a[k], b[k]));
    };
    const hash = v => typeof v === 'string' && /^[0-9a-fA-F]{64}$/.test(v);
    if (!object(data) || data.model_id !== 'thermal_lumped_constant_segments_v1' ||
        data.status !== 'SCREENING_COMPUTED' || data.schema_version !== 'thermal_screening_request_v1' ||
        data.evidence_level !== 'unverified' || data.aircraft_status !== null || data.feasibility !== null ||
        !own(data, 'inputs') || !exact(data.inputs, req) || !hash(data.input_sha256) || !hash(data.evaluation_sha256)) return false;
    const names = ['segments', 'elapsed_s', 'final_temperature_k', 'maximum_temperature_k', 'total_heat_input_j', 'total_convective_exchange_j', 'total_storage_change_j', 'total_energy_balance_residual_j'];
    const units = ['s', 'K', 'K', 'J', 'J', 'J', 'J'];
    const out = data.outputs, outputUnits = data.output_units;
    if (!keys(out, names) || !keys(outputUnits, names) ||
        !names.slice(1).every((k, i) => Number.isFinite(out[k]) && outputUnits[k] === units[i])) return false;
    const segments = out.segments;
    if (!Array.isArray(segments) || segments.length !== 1) return false;
    const fields = ['index', 'duration_s', 'cumulative_elapsed_s', 'start_temperature_k', 'end_temperature_k', 'ambient_temperature_k', 'heat_input_j', 'thermal_storage_change_j', 'convective_exchange_j', 'energy_balance_residual_j'];
    const rowUnits = ['1', 's', 's', 'K', 'K', 'K', 'J', 'J', 'J', 'J'];
    const row = segments[0];
    return keys(row, fields) && keys(outputUnits.segments, fields) &&
      fields.every((k, i) => Number.isFinite(row[k]) && outputUnits.segments[k] === rowUnits[i]);
  } catch (_) {
    return false;
  }
}
export function mountThermal(root,{api,readContext,isContext}) {
  const doc=root.ownerDocument;
  const node=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const test=(e,key)=>{e.dataset.testid='thermal-'+key;return e;};
  const fields=[['mass_kg','Mass (kg)'],['specific_heat_j_kg_k','Specific heat (J/kg/K)'],['initial_temperature_k','Initial temperature (K)'],['lumped_biot_number','Declared Biot number (0 to 0.1)'],['duration_s','Segment duration (s)'],['ambient_temperature_k','Ambient temperature (K)'],['heat_input_w','Heat input (W)'],['conductance_w_k','Conductance hA (W/K)']];
  const section=node('section',undefined,'thermal-screening');
  section.append(node('h2','Lumped thermal screening'),node('p','One constant segment. Independent of aircraft configuration and saved project settings.'));
  section.append(node('p','Uniform temperature and constant properties are assumed. Source and Biot are declarations, not verified applicability. Binary64 numerical limits may cause refusal. No radiation, hotspots, phase change, chemistry, runaway, failure threshold, aircraft safety or feasibility assessment.','thermal-warning'));
  const form=node('form'),grid=node('div',undefined,'thermal-grid'),inputs=new Map();form.noValidate=true;
  for(const [key,label] of fields){const wrap=node('label'),e=test(node('input'),key);e.type='number';e.step='any';e.required=true;wrap.append(node('span',label),e);grid.append(wrap);inputs.set(key,e);}
  const wrap=node('label'),source=test(node('textarea'),'source');source.rows=3;source.required=true;wrap.append(node('span','Property and heat/conductance source declaration (1 to 2000 characters)'),source);
  const run=test(node('button','Run thermal screening'),'run');run.type='submit';run.disabled=true;
  const status=test(node('p','Enter all inputs and source declaration.'),'status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const result=test(node('div',undefined,'thermal-result'),'result');result.hidden=true;form.append(grid,wrap,run);section.append(form,status,result);root.append(section);
  let serial=0,busy=false,ctx=readContext();
  function request(){const v={};for(const [key,e] of inputs){if(!e.value.trim()||e.validity.badInput)return null;v[key]=Number(e.value);if(!Number.isFinite(v[key]))return null;}
    if(['mass_kg','specific_heat_j_kg_k','initial_temperature_k','duration_s','ambient_temperature_k'].some(k=>v[k]<=0)||v.heat_input_w<0||v.conductance_w_k<0||v.lumped_biot_number<0||v.lumped_biot_number>0.1||!source.value.trim()||Array.from(source.value).length>2000)return null;
    const {duration_s,ambient_temperature_k,heat_input_w,conductance_w_k,...base}=v;return {evaluation:'lumped_thermal_screening',...base,property_source:source.value,segments:[{duration_s,ambient_temperature_k,heat_input_w,conductance_w_k}]};}
  function clear(){result.replaceChildren();result.hidden=true;}
  function refresh(){run.disabled=busy||!request();}
  function syncContext(){if(isContext(ctx))return false;ctx=readContext();++serial;busy=false;inputs.forEach(e=>e.value='');source.value='';clear();refresh();status.textContent='Connection changed. Re-enter inputs after connecting.';return true;}
  function current(id,snapshot){if(!isContext(snapshot)){syncContext();return false;}return id===serial;}
  form.addEventListener('input',()=>{syncContext();++serial;busy=false;clear();refresh();status.textContent=request()?'Ready for single-segment screening.':'Enter all required values within the declared ranges.';});
  const labels={elapsed_s:'Elapsed time (s)',final_temperature_k:'Final temperature (K)',maximum_temperature_k:'Maximum endpoint temperature (K)',total_heat_input_j:'Heat input (J)',total_storage_change_j:'Thermal storage change (J)',total_convective_exchange_j:'Signed heat lost to ambient (J)',total_energy_balance_residual_j:'Arithmetic energy residual (J)'};
  function render(data,req){const list=node('dl');for(const [key,label] of Object.entries(labels))list.append(node('dt',label),node('dd',String(data.outputs[key])));result.append(list,node('p','SCREENING_COMPUTED. Evidence unverified. Aircraft status and feasibility unavailable.'),node('p','Energy residual is an arithmetic conservation check, not physical validation or an acceptance threshold. Positive convection is heat lost; negative convection is heat gained.'),node('p','Source declaration: '+req.property_source),node('p','Declared Biot: '+req.lumped_biot_number+'. This is not a measured or independently verified Biot number.'));
    const hashes=node('dl');hashes.append(node('dt','Input SHA-256'),node('dd',data.input_sha256),node('dt','Evaluation SHA-256'),node('dd',data.evaluation_sha256));result.append(hashes,node('p','Hash format is checked here; this is not independent authenticity verification.'));result.hidden=false;}
  form.addEventListener('submit',async event=>{event.preventDefault();if(syncContext()||busy)return;const req=request();if(!req)return;const snapshot=readContext(),id=++serial;busy=true;clear();refresh();status.textContent='Computing declared thermal segment...';try{const response=await api('/thermal/screen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});if(!current(id,snapshot))return;const data=response&&typeof response.json==='function'?await response.json():response;if(!current(id,snapshot))return;
      if(data?.status==='MODEL_INAPPLICABLE'||data?.status==='SOLVER_UNSUPPORTED'){status.textContent=data.status+': '+(Array.isArray(data.reasons)?data.reasons.filter(v=>typeof v==='string').join('; '):'Check model inputs and supported numerical range.');return;}
      if(response?.ok===false||!validThermal(data,req))throw new Error('Invalid response');render(data,req);status.textContent='SCREENING_COMPUTED - unverified thermal screening.';
    }catch{if(current(id,snapshot)){clear();status.textContent='Thermal screening failed. Check connection and inputs.';}}finally{if(current(id,snapshot)){busy=false;refresh();}}});
  return {syncContext};
}
