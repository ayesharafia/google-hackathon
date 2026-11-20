// Transport/presentation only. Existing backend models own equations and refusal gates.
const models = {
  aero: {
    title:'Run simulation — Fixed-wing aerodynamic screening', path:'/fixed-wing/screen',
    model:'fixed_wing_supplied_coefficient_screening_v1', schema:'fixed_wing_screening_request_v1', status:'SCREENING_COMPUTED',
    fixed:{configuration:'fixed_wing',evaluation:'fixed_wing_aerodynamic_screening'},
    scope:'For a declared fixed wing only. Uses supplied coefficients, not uploaded CAD or CFD. No stall, trim, propulsion or flight approval.',
    fields:[['density_kg_m3','Air density (kg/m³)'],['airspeed_m_s','Airspeed (m/s)'],['wing_area_m2','Wing area (m²)'],['span_m','Wingspan (m)'],['characteristic_length_m','Reference length (m)'],['dynamic_viscosity_pa_s','Dynamic viscosity (Pa·s)'],['speed_of_sound_m_s','Speed of sound (m/s)'],['lift_coefficient','Lift coefficient CL'],['zero_lift_drag_coefficient','Zero-lift drag coefficient CD₀'],['span_efficiency','Span efficiency'],['coefficient_envelope.mach_min','Coefficient envelope: minimum Mach'],['coefficient_envelope.mach_max','Coefficient envelope: maximum Mach'],['coefficient_envelope.reynolds_min','Coefficient envelope: minimum Reynolds number'],['coefficient_envelope.reynolds_max','Coefficient envelope: maximum Reynolds number'],['coefficient_envelope.lift_coefficient_min','Coefficient envelope: minimum CL'],['coefficient_envelope.lift_coefficient_max','Coefficient envelope: maximum CL'],['coefficient_source','Coefficient source and applicability','text']],
    units:{dynamic_pressure_pa:'Pa',aspect_ratio:'1',induced_drag_coefficient:'1',drag_coefficient:'1',lift_n:'N',drag_n:'N',drag_power_w:'W',reynolds_number:'1',mach_number:'1'},
  },
  propulsion: {
    title:'Propulsion — experimental isolated-hover rotor',path:'/hover-bemt/evaluate',
    model:'isolated_hover_small_angle_bemt_v1',schema:'hover_bemt_request_v1',status:'COMPUTED_EXPERIMENTAL',
    fixed:{evaluation:'isolated_hover_bemt_experimental'},
    scope:'An isolated rotor in static hover, not cruise propulsion or a motor/battery system. Experimental small-angle model; no stall, swirl or loss factors. Physical validation is not established.',
    fields:[['radius_m','Rotor radius (m)'],['angular_speed_rad_s','Angular speed (rad/s)'],['density_kg_m3','Air density (kg/m³)'],['blade_count','Blade count','integer'],['chord_m','Blade chord (m)'],['lift_curve_slope_per_rad','Lift-curve slope (1/rad)'],['profile_drag_coefficient','Profile drag coefficient'],['pitch_tip_rad','Tip pitch (rad)'],['root_cutout_fraction','Root cutout fraction'],['twist_law','Twist law','constant|hyperbolic|linear'],['annuli','Number of annuli','integer'],['pitch_root_rad','Root pitch (rad; required for linear twist)','optional'],['property_source','Property source','text'],['applicability_declaration','Applicability declaration','text']],
    units:{radial_fraction:'1',inflow_ratio:'1',pitch_rad:'rad',approx_inflow_angle_rad:'rad',approx_angle_of_attack_rad:'rad',thrust_coefficient:'1',blade_thrust_coefficient:'1',induced_power_coefficient:'1',profile_power_coefficient:'1',shaft_power_coefficient:'1',thrust_n:'N',shaft_power_w:'W',shaft_torque_nm:'N*m',thrust_balance_coefficient:'1',max_local_balance_coefficient:'1',annuli:'1'},
  },
  structure: {
    title:'Structure — ideal rectangular cantilever',path:'/cantilever/screen',
    model:'rectangular_cantilever_linear_screening_v1',schema:'cantilever_screening_request_v1',status:'SCREENING_COMPUTED',
    fixed:{evaluation:'rectangular_cantilever_screening'},
    scope:'A prismatic rectangular beam with an ideal fixed root and small deflection. Not an STL-based structural solve, FEM, yield, buckling, fatigue or aircraft strength approval.',
    fields:[['length_m','Beam length (m)'],['width_m','Beam width (m)'],['depth_m','Beam depth (m)'],['youngs_modulus_pa','Young’s modulus (Pa)'],['tip_load_n','Tip load (N)'],['uniform_load_n_m','Uniform load (N/m)'],['declared_min_slenderness','Declared minimum slenderness'],['declared_max_deflection_ratio','Declared maximum deflection / length'],['declared_max_slope_rad','Declared maximum slope (rad)'],['property_source','Material property source','text'],['applicability_declaration','Applicability declaration','text']],
    units:{second_moment_m4:'m^4',flexural_rigidity_n_m2:'N*m^2',root_shear_magnitude_n:'N',root_moment_magnitude_n_m:'N*m',tip_deflection_m:'m',tip_slope_rad:'rad',root_outer_fiber_stress_magnitude_pa:'Pa',slenderness:'1',deflection_ratio:'1'},
  },
};
const equal=(a,b)=>a===b || (a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'&&Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k])));
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const finite=v=>typeof v==='number'&&Number.isFinite(v);

export function mountComponentCalculations(root) {
  const doc=root.ownerDocument, saved=new Map(), failures=new Map(), panels=new Map();
  let generation=0, connected=false, connecting=false;
  const node=(tag,text,cls)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  root.append(node('h2','Optional component calculations'),node('p','Run an existing backend model with explicit data. Each result is independent. Fixed-wing airspeed is entered independently from mission flight speed; all model inputs must be supplied. No combined aircraft result is calculated.'));
  const connection=node('form'), token=node('input'), connect=node('button','Connect'), forget=node('button','Disconnect'), access=node('p','Checking local access…');
  token.type='password';token.autocomplete='off';token.id='calculation-token';
  const tokenLabel=node('label','Development access token');tokenLabel.htmlFor=token.id;
  connect.type='submit';forget.type='button';access.setAttribute('role','status');
  connection.className='calculation-access';connection.append(tokenLabel,token,connect,forget);root.append(connection,access);
  const info=node('p','Use your local development token to run calculations. It is never included in exports.','fineprint');root.append(info);
  function updateAccess(){token.hidden=tokenLabel.hidden=connect.hidden=connected;forget.hidden=!connected;access.textContent=connected?'Connected to local calculations.':'Not connected. Enter your development access token.';panels.forEach(p=>p.update());}
  function invalidate(){++generation;saved.clear();failures.clear();panels.forEach(p=>p.clear());}
  connection.addEventListener('submit',async e=>{
    e.preventDefault();if(connecting)return;connecting=true;connect.disabled=true;invalidate();connected=false;
    const credential=token.value;token.value='';
    try{const r=await fetch('/api/session',{method:'POST',credentials:'same-origin',headers:{Authorization:'Bearer '+credential}});const data=await r.json();connected=r.ok&&data.connected===true;}catch{connected=false;}
    connecting=false;connect.disabled=false;updateAccess();
  });
  forget.addEventListener('click',async()=>{invalidate();connected=false;updateAccess();try{await fetch('/api/session',{method:'DELETE',credentials:'same-origin'});}catch{access.textContent='Disconnected here; server sign-out could not be confirmed.';}});
  const initialGeneration=generation;
  fetch('/api/session',{credentials:'same-origin'}).then(async r=>{const data=await r.json();if(generation===initialGeneration&&!connecting){connected=r.ok&&data.connected===true;updateAccess();}}).catch(()=>{if(generation===initialGeneration)updateAccess();});
  for(const [key,model] of Object.entries(models)){
    const section=node('details'),title=node('summary',model.title),form=node('form'),grid=node('div',undefined,'calculation-fields'),fields=new Map();
    section.dataset.calculation=key;section.append(title,node('p',model.scope));
    for(const [name,label,type] of model.fields){
      const wrap=node('label',label),input=node(type==='text'?'textarea':type?.includes('|')?'select':'input');
      input.name=name;input.dataset.field=name;input.required=type!=='optional';
      if(type==='text'){input.maxLength=2000;input.rows=2;}
      else if(type?.includes('|')){input.append(node('option','Select twist law'));input.firstChild.value='';for(const choice of type.split('|')){const option=node('option',choice);option.value=choice;input.append(option);}}
      else{input.type='number';input.step=type==='integer'?'1':'any';}
      wrap.append(input);grid.append(wrap);fields.set(name,input);if(key==='aero'&&name==='airspeed_m_s'){wrap.append(node('small','Speed relative to the surrounding air. Enter independently from mission flight speed.'));}
    }
    const run=node('button',key==='aero'?'Run simulation':'Run component calculation','primary'),status=node('p','Enter explicit component data to calculate.'),result=node('div',undefined,'component-result');
    run.type='submit';run.dataset.run=key;status.setAttribute('role','status');result.hidden=true;
    form.append(grid,run);section.append(form,status,result);root.append(section);
    let serial=0,busy=false;
    function eligible(){return key!=='aero'||doc.querySelector('[data-aircraft="fixed-wing"]').getAttribute('aria-pressed')==='true';}
    function update(){if(key==='aero')section.hidden=!eligible();run.disabled=!connected||busy||!eligible();if(!eligible())status.textContent='Choose Fixed-wing to use this fixed-wing model.';}
    function clear(){++serial;busy=false;saved.delete(key);failures.delete(key);result.replaceChildren();result.hidden=true;status.textContent='Inputs changed or context reset. Run again for a current result.';update();}
    panels.set(key,{clear,update});update();
    form.addEventListener('input',clear);form.addEventListener('change',clear);
    function request(){
      if(!form.reportValidity())return null;
      const body={...model.fixed};
      for(const [name,,type] of model.fields){
        const raw=fields.get(name).value.trim();
        const value=type==='text'||type?.includes('|')?raw:raw===''&&type==='optional'?null:Number(raw);
        if(type!=='text'&&!type?.includes('|')&&value!==null&&(!finite(value)||(type==='integer'&&!Number.isSafeInteger(value))))return null;
        const [parent,child]=name.split('.');if(child){body[parent]??={};body[parent][child]=value;}else body[name]=value;
      }
      return body;
    }
    form.addEventListener('submit',async e=>{
      e.preventDefault();if(busy||!connected||!eligible())return;
      const body=request();if(!body)return;
      clear();const id=serial,context=generation;busy=true;update();status.textContent='Calculating with the existing backend model…';
      const current=()=>id===serial&&context===generation&&connected&&eligible();
      try{
        const response=await fetch('/api/drone'+model.path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const raw=await response.text();if(!current())return;
        if(!response.ok){if(response.status===401){connected=false;invalidate();updateAccess();}else status.textContent='Calculation refused ('+response.status+'). Check required values and model limits.';return;}
        const data=JSON.parse(raw);
        if(data.model_id!==model.model||data.schema_version!==model.schema||!equal(data.inputs,body)||data.evidence_level!=='unverified'||data.aircraft_status!==null||data.feasibility!==null||!hash(data.input_sha256)||!hash(data.evaluation_sha256))throw new Error('Invalid response');
        if(key==='propulsion'&&data.physical_validation!=='NOT_ESTABLISHED')throw new Error('Invalid evidence');
        if(data.status!==model.status){
          if(!['MODEL_INAPPLICABLE','SOLVER_UNSUPPORTED'].includes(data.status)||!equal(data.outputs,{})||!equal(data.output_units,{}))throw new Error('Invalid refusal');
          const reason=Array.isArray(data.reasons)?data.reasons.filter(x=>typeof x==='string').join('; '):'Outside this model’s supported range.';
          failures.set(key,{discipline:key,reason});status.textContent='Not computed: '+reason;return;
        }
        if(!equal(data.output_units,model.units)||!data.outputs||Object.keys(data.outputs).length!==Object.keys(model.units).length)throw new Error('Invalid output units');
        for(const name of Object.keys(model.units)){
          const value=data.outputs[name];const array=key==='propulsion'&&['radial_fraction','inflow_ratio','pitch_rad','approx_inflow_angle_rad','approx_angle_of_attack_rad'].includes(name);
          if(array?(!Array.isArray(value)||value.length!==body.annuli||!value.every(finite)):!finite(value))throw new Error('Invalid output');
        }
        if(!current())return;
        saved.set(key,{discipline:key,model_scope:model.scope,response_text:raw});
        const table=node('dl');
        for(const [name,value] of Object.entries(data.outputs)){
          if(Array.isArray(value))continue;
          table.append(node('dt',name.replaceAll('_',' ')),node('dd',String(value)+' '+model.units[name]));
        }
        result.append(node('p',model.scope),table,node('p','Evidence: unverified. No aircraft approval or coupled full analysis.'),node('p','Input SHA-256: '+data.input_sha256),node('p','Evaluation SHA-256: '+data.evaluation_sha256));
        if(Array.isArray(data.limitations))for(const limit of data.limitations){if(typeof limit==='string')result.append(node('p',limit,'fineprint'));}
        const download=node('button','Download exact component result');download.type='button';download.addEventListener('click',()=>{
          const url=URL.createObjectURL(new Blob([raw],{type:'application/json'})),a=node('a');a.href=url;a.download='PHYSIMESH_'+key+'_component.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        });result.append(download);result.hidden=false;status.textContent=data.status+' — component result only; evidence unverified.';
      }catch{if(current())status.textContent='Calculation unavailable: invalid response or connection failure. No result retained.';}
      finally{if(id===serial&&context===generation){busy=false;update();}}
    });
  }
  return {invalidate,failures:()=>[...failures.values()].map(failure=>({...failure})),records:()=>[...saved.values()].map(record=>({...record}))};
}
