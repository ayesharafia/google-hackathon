/* Explicit reference-atmosphere preview. No saved-project side effects. */
export const ATMOSPHERE_MODEL='coesa1976.lower-atmosphere.0-30km.v1';
export function atmosphereInputs(altitude,kind){
  if(typeof altitude!=='number'||!Number.isFinite(altitude)||altitude<0||altitude>30000)throw new Error('Enter altitude from 0 to 30000 metres.');
  if(!['geometric','geopotential'].includes(kind))throw new Error('Choose the altitude convention explicitly.');
  return {model_id:ATMOSPHERE_MODEL,altitude_m:altitude,altitude_kind:kind};
}
export function atmosphereDraft(snapshot,result,inputs){
  const v=result?.atmosphere_values,o=result?.outputs;
  if(result?.model?.model_id!==ATMOSPHERE_MODEL||!result?.inputs||Object.keys(inputs).some(key=>result.inputs[key]!==inputs[key])||result?.evidence_level!=='unverified'||result?.aircraft_status!==null||!v||!o||![o.pressure_pa,o.temperature_k,o.density_kg_m3].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>0)||v.pressure_pa!==o.pressure_pa||v.temperature_k!==o.temperature_k||v.altitude_m!==inputs.altitude_m||typeof v.source!=='string'||!v.source.includes(inputs.altitude_kind))throw new Error('Atmosphere response is incomplete or differs from the preview request.');
  if(v.gamma!==1.4||v.viscosity?.law!=='sutherland'||v.viscosity?.value_pa_s!==null)throw new Error('Atmosphere response has unsupported gamma or viscosity.');
  if(!snapshot?.atmosphere||typeof snapshot.atmosphere!=='object'||Array.isArray(snapshot.atmosphere))throw new Error('Draft atmosphere is malformed.');
  const next=structuredClone(snapshot);
  next.atmosphere={...next.atmosphere,source:v.source,altitude_m:v.altitude_m,pressure_pa:v.pressure_pa,temperature_k:v.temperature_k,viscosity:{law:'sutherland',value_pa_s:null},gamma:1.4};
  return next;
}
export function mountAtmospherePreview(container,{read,apply,evaluate}){
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const box=node('fieldset');box.append(node('legend','Standard atmosphere preview'),node('p','Dry reference atmosphere only, not local weather or aircraft validation. Preview does not change the draft.'));
  const label=node('label','Reference altitude, m'),altitude=node('input');altitude.type='number';altitude.min='0';altitude.max='30000';altitude.step='any';label.append(altitude);
  const kindLabel=node('label','Altitude convention'),kind=node('select');for(const [value,text] of [['','Choose explicitly'],['geometric','Geometric'],['geopotential','Geopotential']]){const option=node('option',text);option.value=value;kind.append(option);}kindLabel.append(kind);kind.setAttribute('aria-label','Altitude convention');
  const preview=node('button','Preview reference atmosphere'),use=node('button','Apply preview to unsaved draft'),output=node('p');preview.type=use.type='button';use.dataset.localDisabled='true';use.disabled=true;
  let serial=0,ready=null;
  const invalidate=()=>{serial++;ready=null;use.disabled=true;use.dataset.localDisabled='true';output.textContent='Preview changed. Evaluate again before applying.';};
  altitude.addEventListener('input',invalidate);kind.addEventListener('change',invalidate);
  preview.addEventListener('click',async()=>{const request=++serial;ready=null;use.disabled=true;use.dataset.localDisabled='true';try{
    const inputs=atmosphereInputs(altitude.value===''?null:Number(altitude.value),kind.value),baseline=JSON.stringify(read());
    output.textContent='Evaluating reference atmosphere…';const result=await evaluate(inputs);
    if(request!==serial||!box.isConnected)return;
    if(JSON.stringify(read())!==baseline)throw new Error('Draft changed while evaluating. Preview again.');
    atmosphereDraft(read(),result,inputs);ready={result,inputs,baseline};
    output.textContent=`${Number(result.outputs.pressure_pa.toPrecision(7))} Pa; ${Number(result.outputs.temperature_k.toPrecision(7))} K; ${Number(result.outputs.density_kg_m3.toPrecision(7))} kg/m³. Reference only. Apply creates unsaved edits; save and freeze remain separate.`;
    use.dataset.localDisabled='false';use.disabled=false;
  }catch(error){if(request===serial&&box.isConnected)output.textContent=error.message;}});
  use.addEventListener('click',()=>{try{if(!ready||JSON.stringify(read())!==ready.baseline)throw new Error('Draft changed. Preview again before applying.');const next=atmosphereDraft(read(),ready.result,ready.inputs);ready=null;use.disabled=true;use.dataset.localDisabled='true';apply(next);}catch(error){invalidate();output.textContent=error.message;}});
  box.append(label,kindLabel,preview,use,output);container.append(box);
}
