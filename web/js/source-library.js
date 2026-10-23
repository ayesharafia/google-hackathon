/* A literal measurement worksheet and project-authorized retained library. */
import {createSourceInspection,renderSourceExplorer} from './source-explorer.js?v=source-explorer-1';
import {renderSourceBinding} from './rotor-source-binding.js?v=source-binding-1';
const fields=['rpm','thrust_n','shaft_torque_nm','power_w'];
const names=['RPM','Thrust','Absorbed shaft torque','Input power'];
const units=[['rpm'],['N','gf','kgf'],['Nm','Ncm'],['W','kW']];
const node=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
const button=(text,run)=>{const el=node('button',text);el.type='button';el.addEventListener('click',run);return el;};
function input(parent,label,type='text') {const wrap=node('label',label),el=node(type==='textarea'?'textarea':'input');if(type!=='textarea')el.type=type;else el.rows=3;if(type==='number')el.step='any';wrap.append(el);parent.append(wrap);return el;}
function select(parent,label,values=[]) {const wrap=node('label',label),el=node('select');el.setAttribute('aria-label',label);el.append(new Option('Choose explicitly',''));for(const v of values)el.append(new Option(v,v));wrap.append(el);parent.append(wrap);return el;}
function download(raw,name,type) {const url=URL.createObjectURL(new Blob([raw],{type})),a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
function table(parent,headers,rows,label){const wrap=node('div');wrap.className='table-scroll';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',label);const table=node('table'),head=node('thead'),tr=node('tr');for(const h of headers){const th=node('th',h);th.scope='col';tr.append(th);}head.append(tr);const body=node('tbody');for(const values of rows){const row=node('tr');for(const v of values)row.append(node('td',v===null||v===undefined?'Missing':String(v)));body.append(row);}table.append(head,body);wrap.append(table);parent.append(wrap);}

export function mountSourceLibrary(parent,options){
  if(!options.sourceRequest)return;
  const root=node('details');root.className='tabular-library';root.append(node('summary','CSV/Excel import and component library'));parent.append(root);
  const area=node('section');root.append(area);area.append(node('h4','Import a rotor measurement table'),node('p','Map literal measurements and declare their test conditions. Missing torque or coverage must be supplied from your source. Importing data does not verify aircraft performance.'));
  const file=input(area,'Measurement table (.csv or .xlsx)','file');file.accept='.csv,.xlsx';
  const status=node('p');status.setAttribute('role','status');status.className='tabular-status';area.append(status);
  const source=node('div');source.className='tabular-fields';area.append(source);
  const delimiter=select(source,'CSV delimiter',['comma','semicolon','tab']);delimiter.value='comma';
  const sheet=select(source,'Excel worksheet');
  const header=input(source,'Header row','number');header.value='1';header.min='1';header.max='5000';
  const columns=node('fieldset');columns.append(node('legend','Column mapping and source units'));columns.className='tabular-mapping';
  const columnInputs={},unitInputs={};for(let i=0;i<fields.length;i++){const row=node('div');row.className='tabular-map-row';columnInputs[fields[i]]=select(row,names[i]+' column');unitInputs[fields[i]]=select(row,names[i]+' source unit',units[i]);columns.append(row);}
  const settings=node('fieldset');settings.append(node('legend','Source identity and test declarations'));settings.className='tabular-declarations';
  const declarationFields=node('div');declarationFields.className='tabular-fields';settings.append(declarationFields);
  const dataset=input(declarationFields,'Dataset ID'),configuration=input(declarationFields,'Configuration ID');
  const kind=select(declarationFields,'Declared source kind',['analytic_fixture','measured']);
  const description=input(declarationFields,'Source description','textarea');description.maxLength=2000;description.parentElement.className='tabular-description';
  const conditions={};for(const [key,label] of [['density_kg_m3','Test air density, kg/m³'],['axial_inflow_m_s','Test axial inflow, m/s'],['pitch_deg','Test pitch, degrees'],['max_continuous_duration_s','Covered continuous duration, s']])conditions[key]=input(declarationFields,label,'number');
  const basis=select(declarationFields,'Recorded power basis',['electrical','shaft']);
  const efficiency=input(declarationFields,'Efficiency, required for shaft power','number'),efficiencySource=input(declarationFields,'Efficiency source, required for shaft power');
  const coverage=input(declarationFields,'Covered RPM intervals (low:high, comma separated)');coverage.placeholder='e.g. 1000:2000';
  const range=node('div');range.className='tabular-fields';const start=input(range,'First data row','number'),end=input(range,'Last data row','number');start.min=end.min='2';start.max=end.max='5000';
  const sourceSample=node('div'),preview=node('div'),binding=node('div');
  const read=button('Read table columns',()=>run(async()=>{
    approvedPreview=null;loaded=false;preview.replaceChildren();binding.replaceChildren();
    const info=await options.sourceRequest('/inspect',body(selection(false)));
    if(info.needs_sheet){sheet.replaceChildren(new Option('Choose explicitly',''),...info.sheets.map(name=>new Option(name,name)));status.textContent='Choose an Excel worksheet, then read its columns.';return;}
    for(const key of fields)columnInputs[key].replaceChildren(new Option('Choose explicitly',''),...info.headers.map((text,i)=>new Option((i+1)+': '+(text||'(blank header)').slice(0,100),String(i+1))));
    start.value=String(Number(header.value)+1);end.value=String(info.row_count);loaded=true;
    sourceSample.replaceChildren(node('p',info.row_count+' source rows. Choose the exact data range; the map contract accepts 2–64 complete measurement rows.'));
    table(sourceSample,info.headers,info.sample,'Original measurement sample; scroll horizontally');
    columns.hidden=settings.hidden=range.hidden=false;status.textContent='Columns loaded. Choose mappings, units and test declarations.';
  }));
  const review=button('Preview SI conversion',()=>run(async()=>{
    const spec=selection(true),result=await options.sourceRequest('/preview',body(spec));
    preview.replaceChildren(node('h4',result.valid?'Conversion ready for review':'Conversion needs corrections'),node('p',result.included_rows+' complete rows; '+result.blank_rows+' blank rows; '+result.errors.length+' reported issues.'));
    if(result.errors.length){const list=node('ul');for(const error of result.errors)list.append(node('li',(error.row?'Row '+error.row+', ':'')+error.field+': '+error.message));preview.append(list);}
    const headers=['Source row',...names.flatMap((name,i)=>[name+' original ('+spec.units[fields[i]]+')',name+(i===0?' normalized (rpm)':' SI ('+['rpm','N','Nm','W'][i]+')')])];
    table(preview,headers,result.rows.map(row=>[row.row,...fields.flatMap(key=>[row.original[key],row.si[key]])]),'Original and SI measurement values; scroll horizontally');
    preview.append(node('p','Force, torque and power use N, Nm and W. Speed remains in rpm for the existing map contract.'));
    preview.append(node('p','Conversion factors: '+fields.map(key=>key+' × '+result.factors[key]).join('; ')));
    approvedPreview=result.valid?JSON.stringify(spec):null;status.textContent=result.valid?'Review the SI values, then save this source to the library.':'Correct the reported rows or declarations, then preview again.';
  }));
  const save=button('Save source to library',()=>run(async()=>{
    const spec=selection(true);if(approvedPreview!==JSON.stringify(spec))throw new Error('Preview the current mapping and declarations before saving.');
    const receipt=await options.sourceRequest('/save',body(spec));showReceipt(receipt);status.textContent='Source saved to the library. Choose matching rotors below to change this draft.';
  }));
  area.append(read,sourceSample,range,columns,settings,review,preview,save,binding);
  columns.hidden=settings.hidden=range.hidden=true;
  let loaded=false,serial=0,pending=false,approvedPreview=null;
  const enabled=()=>file.isConnected&&!file.disabled;
  function state(){area.setAttribute('aria-busy',String(pending));for(const [el,disabled] of [[read,!file.files?.length||pending],[review,!loaded||pending],[save,!approvedPreview||pending]]){el.dataset.localDisabled=String(disabled);el.disabled=disabled||!enabled();}}
  function invalidate(reset=false){++serial;approvedPreview=null;preview.replaceChildren();binding.replaceChildren();if(reset){loaded=false;sourceSample.replaceChildren();columns.hidden=settings.hidden=range.hidden=true;}state();}
  function sourceSelection(){return {delimiter:{comma:',',semicolon:';',tab:'\t'}[delimiter.value],sheet:sheet.value,header_row:Number(header.value)};}
  function selection(full){if(!file.files?.[0])throw new Error('Choose a CSV or .xlsx measurement table.');if(file.files[0].size>2*1024*1024)throw new Error('File exceeds 2 MiB.');const result=sourceSelection();if(!full)return result;
    const declarations={dataset_id:dataset.value,configuration_id:configuration.value,source_kind:kind.value,source_description:description.value,torque_convention:'absorbed_shaft_magnitude',power_basis:basis.value};
    for(const [key,el] of Object.entries(conditions))declarations[key]=el.value===''?null:Number(el.value);
    const parts=coverage.value.split(',').map(text=>text.trim());if(!coverage.value||parts.some(text=>!/^\s*[0-9]+(?:\.[0-9]+)?\s*:\s*[0-9]+(?:\.[0-9]+)?\s*$/.test(text)))throw new Error('Declare covered RPM intervals as low:high, separated by commas.');
    declarations.covered_intervals_rpm=parts.map(text=>text.split(':').map(Number));
    if(efficiency.value!=='')declarations.efficiency=Number(efficiency.value);if(efficiencySource.value!=='')declarations.efficiency_source=efficiencySource.value;
    return {...result,start_row:Number(start.value),end_row:Number(end.value),columns:Object.fromEntries(fields.map(key=>[key,Number(columnInputs[key].value)])),units:Object.fromEntries(fields.map(key=>[key,unitInputs[key].value])),declarations};
  }
  function body(spec){const form=new FormData();form.append('file',file.files[0]);form.append('spec',JSON.stringify(spec));return {method:'POST',body:form};}
  async function run(work){if(pending||!enabled())return;const ticket=serial;pending=true;state();status.textContent='Reading source…';
    // Guard results even when mapping controls, rather than draft inputs, change.
    const original=options.sourceRequest;const guarded=async(...args)=>{const result=await original(...args);if(ticket!==serial||!file.isConnected)throw new Error('Import settings changed. Read or preview the current source again.');return result;};
    options={...options,sourceRequest:guarded};
    try{await work();}catch(error){if(file.isConnected){approvedPreview=null;status.textContent=error.message;}}finally{options={...options,sourceRequest:original};pending=false;state();}
  }
  function showReceipt(receipt){renderSourceBinding(binding,receipt,options.read(),{read:options.read,enabled,apply:options.apply});}
  file.addEventListener('change',()=>{invalidate(true);sheet.replaceChildren(new Option('Choose explicitly',''));status.textContent=file.files[0]?'Read the table columns to begin.':'';});
  for(const el of [delimiter,sheet,header])el.addEventListener('change',()=>invalidate(true));
  for(const el of [...Object.values(columnInputs),...Object.values(unitInputs),dataset,configuration,kind,description,...Object.values(conditions),basis,efficiency,efficiencySource,coverage,start,end])el.addEventListener('input',()=>invalidate());

  const library=node('section');library.className='source-catalog';library.append(node('h4','Saved rotor sources'),node('p','Reuse sources from projects you can read. Test conditions and aircraft applicability still require engineering review.'));root.append(library);
  const query=input(library,'Search dataset or configuration'),list=node('div'),detail=node('div'),catalogStatus=node('p');catalogStatus.setAttribute('role','status');
  query.dataset.libraryRead='true';detail.className='source-catalog-detail';
  const readButton=(label,run)=>{const el=button(label,run);el.dataset.libraryRead='true';return el;};
  let cursor=null,catalogSerial=0,searchValue='';
  const inspection=createSourceInspection({
    fetchSource:id=>options.sourceRequest('/'+id),isCurrent:()=>file.isConnected,
    clear:()=>detail.replaceChildren(),render:renderInspection,
    setState:(state,message)=>{detail.setAttribute('aria-busy',String(state==='pending'));catalogStatus.textContent=message;},
  });
  async function browse(more=false){const ticket=++catalogSerial;try{const term=query.value;if(!more){cursor=null;list.replaceChildren();inspection.invalidate('Loading matching sources…');}const result=await options.sourceRequest('?query='+encodeURIComponent(term)+(more&&cursor?'&after='+cursor:''));if(ticket!==catalogSerial||!file.isConnected||query.value!==term)return;searchValue=term;cursor=result.next_cursor;
    for(const entry of result.entries){const item=node('div');item.className='source-catalog-entry';item.append(node('strong',entry.dataset_id),node('p',entry.configuration_id+' · '+entry.source_kind),node('p','Project '+entry.project_id.slice(-8)+' · record '+entry.manifest_sha256.slice(0,12)),readButton('Inspect source '+entry.dataset_id,()=>inspect(entry.entry_id)));list.append(item);}
    catalogStatus.textContent=result.entries.length?'Sources loaded. Inspect an entry to review its conditions and provenance.':'No accessible sources match this search.';
    next.dataset.localDisabled=String(!cursor);next.disabled=!cursor||query.disabled;
  }catch(error){catalogStatus.textContent=error.message;}}
  function inspect(id){++catalogSerial;return inspection.inspect(id);}
  function renderInspection(receipt,stillSelected){
    const id=receipt.entry.entry_id;
    detail.replaceChildren(node('h4',receipt.dataset.dataset_id),node('p','Configuration '+receipt.dataset.configuration_id+'. Density '+receipt.dataset.density_kg_m3+' kg/m³; inflow '+receipt.dataset.axial_inflow_m_s+' m/s; pitch '+receipt.dataset.pitch_deg+'°; duration '+receipt.dataset.max_continuous_duration_s+' s.'),node('p','Original file: '+receipt.manifest.filename+' · '+receipt.manifest.file_sha256),node('p',receipt.qualification));
    renderSourceExplorer(detail,receipt,{canRead:()=>stillSelected()&&!query.disabled});
    const record=node('details');record.append(node('summary','Conversion record'),node('pre',JSON.stringify(receipt.manifest,null,2)));detail.append(record,
      readButton('Download conversion record',()=>{if(stillSelected())download(JSON.stringify(receipt.manifest,null,2),'rotor-conversion.json','application/json');}),
      readButton('Download original file',async()=>{if(!stillSelected())return;try{await options.sourceDownload(id,receipt.manifest.filename);if(stillSelected())catalogStatus.textContent='Original file download requested.';}catch(error){if(stillSelected())catalogStatus.textContent=error.message;}}),
      button('Use source in this project',async()=>{if(!stillSelected())return;try{const copy=await options.sourceRequest('/'+id+'/reuse',{method:'POST'});if(!stillSelected())return;showReceipt(copy);catalogStatus.textContent='Source available in this project. Explicitly choose matching rotors in the import section.';binding.scrollIntoView({block:'nearest'});}catch(error){if(stillSelected())catalogStatus.textContent=error.message;}}));
    detail.querySelectorAll('button:not([data-library-read])').forEach(el=>{el.disabled=!enabled();});
  }
  query.addEventListener('input',()=>{++catalogSerial;cursor=null;inspection.invalidate('Search changed. Load matching sources.');list.replaceChildren();next.dataset.localDisabled='true';next.disabled=true;});
  const next=readButton('Load more sources',()=>{if(query.value===searchValue&&cursor)browse(true);});next.dataset.localDisabled='true';next.disabled=true;
  library.append(readButton('Load matching sources',()=>browse()),list,next,catalogStatus,detail);state();
}
