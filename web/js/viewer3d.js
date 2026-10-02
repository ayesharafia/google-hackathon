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
  function clear(){group.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material)o.material.dispose();});scene.remove(group);group=new THREE.Group();scene.add(group);}
  function fit(){const box=new THREE.Box3().setFromObject(group);box.getCenter(centre);distance=Math.max(...box.getSize(new THREE.Vector3()).toArray())*1.8;reset();resize();}
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
  function showSurface(data){clear();surface=data;geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));const material=new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide});group.add(new THREE.Mesh(geometry,material));const range=setField(field);fit();return range;}
  function showStl(buffers,scale){clear();surface=null;const loader=new STLLoader();buffers.forEach(buffer=>{const geom=loader.parse(buffer);geom.scale(scale,scale,scale);const material=new THREE.MeshStandardMaterial({color:'#728d78',roughness:.8,metalness:.1,side:THREE.DoubleSide,flatShading:true});group.add(new THREE.Mesh(geom,material));});fit();}
  resize();return {showSurface,setField,showStl,reset};
}
