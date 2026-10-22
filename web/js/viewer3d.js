import * as THREE from 'three';
import {OrbitControls} from '/web/vendor/OrbitControls.js';
import {STLLoader} from '/web/vendor/STLLoader.js';

export function createViewer(container) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#d9e4d9');
  const renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  container.replaceChildren(renderer.domElement); renderer.domElement.setAttribute('aria-label','Interactive native surface. Drag to orbit, scroll to zoom.');
  const camera = new THREE.PerspectiveCamera(38,1,0.001,100000); camera.up.set(0,0,1);
  const controls = new OrbitControls(camera,renderer.domElement); controls.enableDamping=false;
  scene.add(new THREE.AmbientLight('#dce8dd',2));const light=new THREE.DirectionalLight('#ffffff',3);light.position.set(3,-2,5);scene.add(light);
  let group = new THREE.Group(), surface, geometry, field='pressure'; scene.add(group);
  let centre=new THREE.Vector3(), distance=2.8;
  const draw=()=>renderer.render(scene,camera);
  function resize(){const w=container.clientWidth,h=container.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();draw();}
  new ResizeObserver(resize).observe(container); controls.addEventListener('change',draw);
  function reset(){controls.target.copy(centre);camera.position.copy(centre).add(new THREE.Vector3(distance,-distance,distance*.65));camera.near=distance/1000;camera.far=distance*100;camera.updateProjectionMatrix();controls.update();draw();}
  function clear(){group.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material)o.material.dispose();});scene.remove(group);group=new THREE.Group();scene.add(group);surface=null;renderer.domElement.setAttribute('aria-label','Empty 3D preview.');draw();}
  function fit(){const box=new THREE.Box3().setFromObject(group);box.getCenter(centre);const aspect=Math.max(1,container.clientWidth)/Math.max(1,container.clientHeight);distance=Math.max(1e-6,...box.getSize(new THREE.Vector3()).toArray())*1.8/Math.min(1,aspect);reset();resize();}
  function setField(mode){
    if(!surface)return;field=mode;
    const values=mode==='pressure'?surface.pressure_pa:surface.wall_shear_pa;
    const range=mode==='pressure'?surface.pressure_range_pa:surface.shear_range_pa;
    const extent=Math.max(Math.abs(range[0]),Math.abs(range[1]));const lo=mode==='pressure'?-extent:0,hi=mode==='pressure'?extent:range[1];
    const stops=(mode==='pressure'?['#2166ac','#67a9cf','#f7f7f7','#ef8a62','#b2182b']:['#440154','#3b528b','#21918c','#5ec962','#fde725']).map(c=>new THREE.Color(c));
    const colors=new Float32Array(values.length*3);
    values.forEach((v,i)=>{const t=Math.min(1,Math.max(0,(v-lo)/(hi-lo||1)))*(stops.length-1),k=Math.min(stops.length-2,Math.floor(t));const c=stops[k].clone().lerp(stops[k+1],t-k);colors.set([c.r,c.g,c.b],i*3);});
    geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));draw();return {range:[lo,hi],trueRange:range};
  }
  function showSurface(data){clear();surface=data;renderer.domElement.setAttribute('aria-label','Interactive native surface. Drag to orbit, scroll to zoom.');geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));const material=new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide});group.add(new THREE.Mesh(geometry,material));const range=setField(field);fit();return range;}
  function showStl(buffers,scale,transform={}){
    const loader=new STLLoader(),meshes=[];
    try{buffers.forEach(buffer=>{
      const geom=loader.parse(buffer),factor=scale*(transform.scale??1);
      geom.scale(factor,factor,factor);
      const [yaw,pitch,roll]=(transform.rotation_deg_zyx??[0,0,0]).map(THREE.MathUtils.degToRad);
      geom.applyMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(roll,pitch,yaw,'ZYX')));
      geom.translate(...(transform.translation_m??[0,0,0]));
      const material=new THREE.MeshStandardMaterial({color:'#728d78',roughness:.8,metalness:.1,side:THREE.DoubleSide,flatShading:true});
      meshes.push(new THREE.Mesh(geom,material));
    });}catch(error){meshes.forEach(mesh=>{mesh.geometry.dispose();mesh.material.dispose();});throw error;}
    clear();meshes.forEach(mesh=>group.add(mesh));
    renderer.domElement.setAttribute('aria-label','Uploaded STL geometry in metres. Drag to orbit; scroll or pinch to zoom.');fit();
  }
  function showRotorLayout(snapshot,cg,{geometries=[],highlightedRotors=[],failedRotors=[]}={}){
    clear();surface=null;
    const valid=(v)=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite);
    const loader=new STLLoader();let triangles=0;
    geometries.forEach(({buffer,component:c})=>{
      const t=c.transform;
      if(!Number.isFinite(c.unit_scale_to_m)||c.unit_scale_to_m<=0||!t||!Number.isFinite(t.scale)||t.scale<=0||!valid(t.rotation_deg_zyx)||!valid(t.translation_m))throw new Error('Geometry units and body-frame transform must be explicitly declared.');
      const geom=loader.parse(buffer);triangles+=geom.getAttribute('position').count/3;
      if(triangles>1000000){geom.dispose();throw new Error('Assembly preview exceeds one million triangles.');}
      const [yaw,pitch,roll]=t.rotation_deg_zyx.map(v=>v*Math.PI/180);
      geom.scale(c.unit_scale_to_m*t.scale,c.unit_scale_to_m*t.scale,c.unit_scale_to_m*t.scale);
      geom.applyMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(roll,pitch,yaw,'ZYX')));
      geom.translate(...t.translation_m);
      group.add(new THREE.Mesh(geom,new THREE.MeshStandardMaterial({color:'#859989',roughness:.9,side:THREE.DoubleSide,flatShading:true})));
    });
    let count=0;
    (snapshot.rotors||[]).forEach(rotor=>{
      if(!valid(rotor.center_body_m)||!valid(rotor.axis_body))return;
      const pos=new THREE.Vector3(...rotor.center_body_m),axis=new THREE.Vector3(...rotor.axis_body);
      if(Math.abs(axis.length()-1)>1e-9)return;
      if(Number.isFinite(rotor.radius_m)&&rotor.radius_m>0){
        const color=failedRotors.includes(rotor.rotor_id)?'#a53832':highlightedRotors.includes(rotor.rotor_id)?'#bf781f':rotor.rotation_sign===1?'#728d78':'#a4b8a6';
        const disk=new THREE.Mesh(new THREE.CircleGeometry(rotor.radius_m,48),new THREE.MeshStandardMaterial({color,side:THREE.DoubleSide,roughness:.85}));
        disk.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),axis);disk.position.copy(pos);group.add(disk);
        group.add(new THREE.ArrowHelper(axis,pos,rotor.radius_m*2,0x20382c,rotor.radius_m*.3,rotor.radius_m*.15));count++;
      }
    });
    if(valid(cg)){const marker=new THREE.Mesh(new THREE.SphereGeometry(.04,16,12),new THREE.MeshStandardMaterial({color:'#20382c',roughness:.9}));marker.position.set(...cg);group.add(marker);}
    if(count||geometries.length)fit();else{centre.set(0,0,0);distance=2.8;reset();resize();}
    renderer.domElement.setAttribute('aria-label','Declared airframe, rotor disks, axes and CG. Amber disks have active limits; red disks are failed. Drag to orbit; scroll to zoom.');
    return count;
  }
  resize();return {showSurface,setField,showStl,showRotorLayout,reset,clear};
}
