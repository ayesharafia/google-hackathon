// A view of retained source samples. Plot coordinates are display transforms only.
const fields = ['rpm','thrust_n','shaft_torque_nm','power_w'];
const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const number = value => typeof value === 'number' && Number.isFinite(value);
const text = value => typeof value === 'string' && value.trim().length > 0;
const unavailable = reason => ({available:false,reason});
export function sourceIdentityMatches(receipt, id) {
  const {entry,manifest,dataset} = receipt || {};
  return Boolean(entry && manifest && dataset && digest(id) && entry.entry_id === id
    && digest(entry.manifest_sha256) && text(entry.project_id)
    && manifest.schema_version === 'rotor_tabular_import_v1' && manifest.conversion_version === 'literal_si_v1'
    && digest(manifest.file_sha256) && digest(receipt.source_sha256) && manifest.map_sha256 === receipt.source_sha256
    && ['dataset_id','configuration_id','source_kind'].every(key => text(dataset[key]) && entry[key] === dataset[key]));
}
export function sourceExplorerView(receipt) {
  if (!sourceIdentityMatches(receipt,receipt?.entry?.entry_id)) return unavailable('Source identity or conversion format is inconsistent.');
  const d=receipt.dataset, manifest=receipt.manifest;
  if (d.schema_version !== 'rotor_map_v1' || d.units !== 'rpm_N_Nm_W'
      || d.torque_convention !== 'absorbed_shaft_magnitude'
      || !['electrical','shaft'].includes(d.power_basis) || !['measured','analytic_fixture'].includes(d.source_kind))
    return unavailable('Source units, quantity conventions or power basis are unsupported.');
  if (d.power_basis === 'shaft' && (!number(d.efficiency) || d.efficiency <= 0 || d.efficiency > 1 || !text(d.efficiency_source))
      || d.power_basis === 'electrical' && (d.efficiency != null || d.efficiency_source != null))
    return unavailable('Declared power-basis metadata is inconsistent.');
  if (!number(d.density_kg_m3) || d.density_kg_m3 <= 0 || !number(d.axial_inflow_m_s)
      || !number(d.pitch_deg) || !number(d.max_continuous_duration_s) || d.max_continuous_duration_s <= 0)
    return unavailable('Source test conditions are missing or invalid.');
  if (!Array.isArray(d.points) || d.points.length < 2 || d.points.length > 64
      || d.points.some(p => !p || fields.some(key => !number(p[key]) || p[key] < 0))
      || d.points.some((p,i) => i > 0 && p.rpm <= d.points[i-1].rpm))
    return unavailable('Expected 2–64 complete, finite samples in strictly increasing RPM order.');
  if (!Array.isArray(manifest.rows) || manifest.rows.length !== d.points.length
      || manifest.rows.some((row,i) => !row || !Number.isInteger(row.row) || row.row < 1 || row.row > 5000
        || (i > 0 && row.row <= manifest.rows[i-1].row)
        || fields.some(key => row.si?.[key] !== d.points[i][key])))
    return unavailable('Original row mapping differs from the retained normalized samples.');
  const spans=d.covered_intervals_rpm, rpms=d.points.map(p=>p.rpm);
  if (!Array.isArray(spans) || !spans.length || spans.length > 32
      || spans.some(span => !Array.isArray(span) || span.length !== 2 || span.some(v=>!number(v))
        || span[0] >= span[1] || !rpms.includes(span[0]) || !rpms.includes(span[1])))
    return unavailable('Declared RPM coverage is missing or inconsistent with its retained samples.');
  const ordered=spans.map(span=>[...span]).sort((a,b)=>a[0]-b[0]);
  if (ordered.some((span,i)=>i > 0 && span[0] < ordered[i-1][1])) return unavailable('Declared RPM coverage intervals overlap.');
  return {available:true, dataset:d, entry:receipt.entry, source:receipt.source_sha256,
    powerLabel:d.power_basis === 'electrical' ? 'Electrical input power, W' : 'Shaft power, W',
    intervals:spans.map(span=>[...span]), points:d.points.map((p,i)=>({...p,index:i,row:manifest.rows[i].row,
      covered:spans.some(([low,high])=>low <= p.rpm && p.rpm <= high)}))};
}
export function sourcePlot(view, metric='thrust_n', requestedWidth=640) {
  if (!view?.available || !['thrust_n','shaft_torque_nm','power_w'].includes(metric)) return null;
  const width=number(requestedWidth) ? Math.max(260,Math.min(1200,requestedWidth)) : 640;
  const height=300,left=66,right=24,top=22,bottom=230;
  const xMax=view.points.at(-1).rpm, yMax=Math.max(...view.points.map(p=>p[metric]));
  const x=value=>left+(value/xMax)*(width-left-right);
  const y=value=>bottom-(yMax === 0 ? 0 : value/yMax)*(bottom-top);
  return {width,height,left,right,top,bottom,xMax,yMax,
    points:view.points.map(p=>({...p,x:x(p.rpm),y:y(p[metric])})),
    intervals:view.intervals.map(([low,high])=>({low,high,x:x(low),width:x(high)-x(low)})),
    xTicks:[0,0.5,1].map(f=>({value:f*xMax,x:x(f*xMax)})),
    yTicks:(yMax === 0 ? [0] : [0,0.5,1]).map(f=>({value:f*yMax,y:y(f*yMax)}))};
}
export function createSourceInspection({fetchSource,isCurrent,clear,render,setState}) {
  let serial=0;
  return {
    invalidate(message='Choose a source to inspect.') {++serial;clear();setState('idle',message);},
    async inspect(id) {
      const ticket=++serial;clear();setState('pending','Loading selected source…');
      try {
        const receipt=await fetchSource(id);
        if (ticket !== serial || !isCurrent()) return;
        if (!sourceIdentityMatches(receipt,id)) throw new Error('Source response identity differs from the selected library entry.');
        render(receipt,()=>ticket === serial && isCurrent());setState('current','Selected source loaded. Review its retained points, conditions and provenance.');
      } catch(error) {
        if (ticket !== serial || !isCurrent()) return;
        clear();setState('failed','Source inspection unavailable: '+error.message);
      }
    },
  };
}
const el=(tag,value)=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=value;return node;};
const svgEl=(tag,attrs={},value)=>{const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,v] of Object.entries(attrs))node.setAttribute(key,String(v));if(value!==undefined)node.textContent=value;return node;};
const compact=value=>value === 0 ? '0' : value >= 100000 || value < 0.01 ? value.toExponential(2) : String(Number(value.toPrecision(3)));
let sequence=0;
export function renderSourceExplorer(parent,receipt,{canRead=()=>true}={}) {
  const root=el('section');root.className='source-explorer';root.setAttribute('aria-label','Rotor source explorer');parent.append(root);
  root.append(el('h5','Retained source samples'));
  const view=sourceExplorerView(receipt);
  if (!view.available) {root.append(el('p','Source explorer unavailable: '+view.reason));return;}
  root.dataset.source= view.source;root.dataset.entry=view.entry.entry_id;
  root.append(el('p',view.dataset.source_kind === 'analytic_fixture' ? 'Illustrative analytic fixture. These samples are not measured aircraft evidence.'
    : 'Declared measured source. Measurement quality and aircraft applicability remain unverified.'),
    el('p','Discrete retained points; no fitting, smoothing or extrapolation. Coverage bars show the declared RPM intervals. Hollow markers are samples outside those intervals.'));
  const identity=el('p','Source project '+view.entry.project_id+'\nRetained map '+view.source);identity.className='source-explorer-binding';root.append(identity);
  const controls=el('div');controls.className='source-explorer-controls';
  const metricLabel=el('label','Plot quantity'),metric=el('select');metric.setAttribute('aria-label','Plot quantity');metric.dataset.libraryRead='true';
  for(const [key,label] of [['thrust_n','Thrust, N'],['shaft_torque_nm','Absorbed shaft torque, Nm'],['power_w',view.powerLabel]]){const option=el('option',label);option.value=key;metric.append(option);}
  const sampleLabel=el('label','Retained sample'),sample=el('select');sample.setAttribute('aria-label','Retained sample');sample.dataset.libraryRead='true';
  for(const point of view.points){const option=el('option','Original row '+point.row);option.value=String(point.index);sample.append(option);}
  metricLabel.append(metric);sampleLabel.append(sample);controls.append(metricLabel,sampleLabel);root.append(controls);
  const figure=el('figure'),caption=el('figcaption'),svg=svgEl('svg',{role:'group',height:300});figure.append(caption,svg);root.append(figure);
  const state=el('p');state.className='source-sample-status';state.setAttribute('role','status');root.append(state);
  const readout=el('dl');readout.className='source-sample-values';root.append(readout);
  const scroll=el('div');scroll.className='table-scroll';scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Exact retained rotor samples. Scroll horizontally for every quantity.');
  const table=el('table'),head=el('thead'),hr=el('tr'),body=el('tbody');
  ['Original row','RPM','Thrust, N','Shaft torque, Nm',view.powerLabel,'Declared RPM coverage'].forEach(label=>{const th=el('th',label);th.scope='col';hr.append(th);});head.append(hr);
  view.points.forEach(point=>{const tr=el('tr');tr.dataset.sourceRow=point.row;const th=el('th',String(point.row));th.scope='row';tr.append(th,...[point.rpm,point.thrust_n,point.shaft_torque_nm,point.power_w,point.covered?'Inside interval':'Outside intervals'].map(value=>el('td',String(value))));body.append(tr);});table.append(head,body);scroll.append(table);
  root.append(el('p','Exact values and original source rows. Scroll the table horizontally for every quantity.'),scroll,
    el('p','Declared coverage, rpm: '+view.intervals.map(([low,high])=>low+' to '+high).join('; ')+'. Power basis: '+view.dataset.power_basis+'.'));
  const uid='source-samples-'+(++sequence);let selected=0;
  const interactive=()=>root.isConnected && canRead() && !metric.disabled && !sample.disabled;
  function drawPlot(focus=false) {
    const focused=svg.contains(document.activeElement),plot=sourcePlot(view,metric.value,figure.clientWidth);
    svg.setAttribute('viewBox',`0 0 ${plot.width} ${plot.height}`);svg.setAttribute('aria-labelledby',uid+'-title');svg.setAttribute('aria-describedby',uid+'-desc');
    caption.textContent=metric.selectedOptions[0].textContent+' against RPM';svg.replaceChildren(
      svgEl('title',{id:uid+'-title'},caption.textContent),
      svgEl('desc',{id:uid+'-desc'},'Retained source sample plot. Bars below the RPM axis show declared coverage. Select a sample for exact values. Left and right arrow keys change the selected point; Home and End select the endpoints.'));
    svg.append(svgEl('path',{d:`M ${plot.left} ${plot.top} V ${plot.bottom} H ${plot.width-plot.right}`,class:'source-axes'}));
    for(const tick of plot.xTicks)svg.append(svgEl('text',{x:tick.x,y:plot.bottom+20,'text-anchor':tick.value===0?'start':tick.value===plot.xMax?'end':'middle',class:'source-tick'},compact(tick.value)));
    for(const tick of plot.yTicks)svg.append(svgEl('text',{x:plot.left-10,y:tick.y+4,'text-anchor':'end',class:'source-tick'},compact(tick.value)));
    plot.intervals.forEach(span=>svg.append(svgEl('rect',{x:span.x,y:260,width:span.width,height:6,class:'source-coverage'})));
    svg.append(svgEl('text',{x:(plot.left+plot.width-plot.right)/2,y:290,'text-anchor':'middle',class:'source-tick'},'RPM'));
    plot.points.forEach(point=>{
      const mark=svgEl('g',{transform:`translate(${point.x} ${point.y})`,role:'button',tabindex:point.index===selected?0:-1,
        'data-source-sample':point.index,'data-selected':point.index===selected,'aria-pressed':point.index===selected,'aria-disabled':!interactive(),
        'aria-label':'Sample from original row '+point.row+', RPM '+point.rpm});
      mark.append(svgEl('circle',{r:12,class:'source-point-target'}),svgEl('circle',{r:point.index===selected?7:4.5,class:'source-point '+(point.covered?'covered':'uncovered')}));svg.append(mark);
    });
    if(focus||focused)svg.querySelector('[data-selected=true]')?.focus({preventScroll:true});
  }
  function update(focus=false) {
    const point=view.points[selected];sample.value=String(selected);state.textContent='Selected original row '+point.row+' · '+(point.covered?'inside declared RPM coverage.':'outside declared RPM coverage.');
    readout.replaceChildren();for(const [label,value] of [['RPM',point.rpm],['Thrust, N',point.thrust_n],['Shaft torque, Nm',point.shaft_torque_nm],[view.powerLabel,point.power_w]]){
      const div=el('div');div.append(el('dt',label),el('dd',String(value)));readout.append(div);
    }
    body.querySelectorAll('tr').forEach((tr,i)=>tr.setAttribute('aria-current',String(i===selected)));drawPlot(focus);
  }
  sample.addEventListener('change',()=>{const index=Number(sample.value);if(interactive()&&Number.isInteger(index)&&index>=0&&index<view.points.length){selected=index;update();}});
  metric.addEventListener('change',()=>{if(interactive())drawPlot();});
  svg.addEventListener('click',event=>{const mark=event.target.closest('[data-source-sample]');if(mark&&interactive()){selected=Number(mark.dataset.sourceSample);update(true);}});
  svg.addEventListener('keydown',event=>{if(!interactive()||!event.target.closest('[data-source-sample]'))return;
    const steps={ArrowRight:Math.min(view.points.length-1,selected+1),ArrowLeft:Math.max(0,selected-1),Home:0,End:view.points.length-1};
    if(event.key in steps){event.preventDefault();selected=steps[event.key];update(true);}else if(['Enter',' '].includes(event.key)){event.preventDefault();update(true);}
  });
  update();
  const observer=new ResizeObserver(()=>{if(!root.isConnected){observer.disconnect();return;}drawPlot();});observer.observe(figure);
}
