import {
  DirectionalLight, Euler, HemisphereLight, Matrix4, PCFShadowMap,
  PerspectiveCamera, Quaternion, Scene, SRGBColorSpace,
  Texture, Vector3, WebGLRenderer,
} from 'three';
import {makeDeck} from './geometry.js';
import {makeShadows} from './shadows.js';

const clamp = (value, low, high) => Math.min(high, Math.max(low,value));
const DEG = Math.PI / 180;

function setAffine(matrix, data, i) {
  matrix.set(data[i],data[i+1],data[i+2],data[i+3],
             data[i+4],data[i+5],data[i+6],data[i+7],
             data[i+8],data[i+9],data[i+10],data[i+11],0,0,0,1);
}

const scores = new WeakMap();
function readScore(packet) {
  let existing=scores.get(packet);
  if(existing)return existing;
  const packed=Uint8Array.from(atob(packet.score),c=>c.charCodeAt(0));
  const stream=new Blob([packed]).stream().pipeThrough(new DecompressionStream('deflate'));
  existing=new Response(stream).arrayBuffer().then(bytes=>{
    const data=new Float32Array(bytes);
    if(data.length!==packet.info.frames*packet.info.stride)throw new Error('Incomplete deck score');
    return data;
  }).catch(error=>{scores.delete(packet);throw error;});
  scores.set(packet,existing);
  return existing;
}

export async function mount(stage, tools, packet, onLoss) {
  const info=packet.info;
  // The native movie is already playing. Leave it in place on systems with no
  // GPU instead of decoding the large atlas and movement score unnecessarily.
  if(typeof DecompressionStream==='undefined')return null;
  const canvas=document.createElement('canvas');
  const context=canvas.getContext('webgl2',{alpha:true,antialias:true,powerPreference:'low-power'});
  if(!context)return null;
  const photo=new Image();
  photo.src='data:image/webp;base64,'+packet.image;
  let data;
  try {
    [data]=await Promise.all([readScore(packet),photo.decode()]);
  } catch(error) {
    context.getExtension('WEBGL_lose_context')?.loseContext();
    throw error;
  }

  const renderer = new WebGLRenderer({canvas, context, alpha:true, antialias:true});
  renderer.setClearColor(0x000000,0);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = PCFShadowMap;
  renderer.outputColorSpace = SRGBColorSpace;
  const texture = new Texture(photo);
  texture.colorSpace = SRGBColorSpace;
  texture.anisotropy = Math.min(4,renderer.capabilities.getMaxAnisotropy());
  texture.needsUpdate = true;
  const scene = new Scene();
  const deck = makeDeck(info,texture);
  scene.add(deck);
  scene.add(new HemisphereLight(0xfffefa,0xbdbdca,1.60));
  const key = new DirectionalLight(0xfff8ee,2.32);
  key.position.set(-3,4,6);
  key.castShadow = true;
  key.shadow.mapSize.set(512,512);
  Object.assign(key.shadow.camera,{left:-3,right:3,top:3,bottom:-3,near:.25,far:13});
  key.shadow.camera.updateProjectionMatrix();
  key.shadow.bias = -.00014;
  key.shadow.normalBias = .0018;
  key.shadow.radius = 2.8;
  key.shadow.intensity = .34;
  scene.add(key);
  const ground = makeShadows(info.casterSlots, info.cardWidth, info.stock);
  const floor = ground.mesh;
  scene.add(floor);
  const camera = new PerspectiveCamera(20,1,.05,40);
  canvas.tabIndex = 0;
  canvas.setAttribute('role','img');
  canvas.setAttribute('aria-label','A complete deck springs from one packet to another, then opens into a fan. Use the orbit controls or arrow keys to inspect it.');
  stage.append(canvas);
  const abort = new AbortController();
  const events = {signal:abort.signal};
  const matrix = new Matrix4(), shot = new Quaternion(), orbit = new Quaternion(), angles = new Euler(0,0,0,'YXZ');
  const focus = new Vector3(), center = new Vector3();
  let width=1,height=1,frameRequest=0,shown=false,paused=false,disposed=false;
  let playhead=0, previous=null, lastFrame=-1;
  let yaw=0,pitch=0,goalYaw=0,goalPitch=0;
  let pointer=null, prevX=0,prevY=0, dirty=true;
  let quality=1, resolution=0, measuredTime=0, intervalCount=0;
  function queue() {
    if (!disposed && shown && !document.hidden && !frameRequest) frameRequest=requestAnimationFrame(draw);
  }
  function setOrbit(x,y) {
    goalYaw=clamp(x,-Math.PI,Math.PI);
    goalPitch=clamp(y,-1.06,1.06);
    dirty=true;
    queue();
  }
  function reset() {setOrbit(0,0);}
  function step(action) {
    const by = 16*DEG;
    if (action==='left') setOrbit(goalYaw-by,goalPitch);
    if (action==='right') setOrbit(goalYaw+by,goalPitch);
    if (action==='up') setOrbit(goalYaw,goalPitch+by);
    if (action==='down') setOrbit(goalYaw,goalPitch-by);
    if (action==='reset') reset();
  }
  tools.addEventListener('click',e=>{
    const command=e.target.closest('[data-orbit]');
    if(command) step(command.dataset.orbit);
  }, events);
  const cue=tools.querySelector('[data-cue]');
  cue.replaceChildren(new Option('Jump to a trick',''));
  for (const item of info.cues) cue.add(new Option(item.name,String(item.time)));
  cue.addEventListener('change',()=>{
    if(cue.value!==''){
      playhead=Number(cue.value);previous=null;dirty=true;
      cue.value='';queue();
    }
  },events);
  canvas.addEventListener('keydown', e=>{
    const action={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down',Home:'reset'}[e.key];
    if(action) {e.preventDefault();step(action);}
  },events);
  canvas.addEventListener('pointerdown',e=>{
    if(!e.isPrimary || e.button!==0) return;
    pointer=e.pointerId;prevX=e.clientX;prevY=e.clientY;
    canvas.focus({preventScroll:true});canvas.setPointerCapture(pointer);
    canvas.dataset.dragging='true';
  },events);
  canvas.addEventListener('pointermove',e=>{
    if(e.pointerId!==pointer) return;
    const dx=e.clientX-prevX,dy=e.clientY-prevY;
    prevX=e.clientX;prevY=e.clientY;
    setOrbit(goalYaw-dx*3.7/width,goalPitch+dy*2.55/height);
  },events);
  canvas.addEventListener('lostpointercapture',()=>{pointer=null;delete canvas.dataset.dragging;},events);
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();if(!disposed)onLoss();},events);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  function resolutionForView() {
    const maximum=Math.min(window.devicePixelRatio || 1,1.65,1150/width);
    return maximum*(paused && pointer===null ? 1 : quality);
  }
  function resize() {
    const rect=stage.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    width=Math.max(1,Math.round(rect.width));height=Math.max(1,Math.round(rect.height));
    resolution=resolutionForView();
    renderer.setPixelRatio(resolution);
    renderer.setSize(width,height,false);
    dirty=true;queue();
  }
  function trackFrameCost(dt) {
    if (paused || dt<=0 || dt>.15 || quality<=.55) return;
    measuredTime+=dt;intervalCount++;
    if (measuredTime<.85 || intervalCount<12) return;
    const average=measuredTime/intervalCount;
    measuredTime=0;intervalCount=0;
    if (average>.0208) {
      // On busy or software GPUs trade render resolution for continuous motion.
      // A paused, stationary deck still uses the display's full texture detail.
      quality=Math.max(.55,quality*Math.max(.74,Math.sqrt((1/59)/average)));
    }
  }
  const observer=new ResizeObserver(resize);
  observer.observe(stage);
  document.addEventListener('visibilitychange',()=>{
    previous=null;
    if(document.hidden) {cancelAnimationFrame(frameRequest);frameRequest=0;}
    else queue();
  },events);

  function draw(now) {
    frameRequest=0;
    if(!shown || disposed || document.hidden) return;
    const dt=previous===null ? 0 : Math.max(0,(now-previous)/1000);
    previous=now;
    trackFrameCost(dt);
    const wanted=resolutionForView();
    if (Math.abs(wanted-resolution)>.01){
      resolution=wanted;renderer.setPixelRatio(wanted);dirty=true;
    }
    if(!paused) playhead=(playhead+dt)%(info.frames/info.fps);
    const frame=Math.floor(playhead*info.fps)%info.frames;
    const settle=reduced.matches ? 1 : 1-Math.exp(-18*Math.min(dt,.2));
    const moving = Math.abs(goalYaw-yaw)+Math.abs(goalPitch-pitch)>.0002;
    if(moving) {yaw+=(goalYaw-yaw)*settle;pitch+=(goalPitch-pitch)*settle;}
    if(!moving){yaw=goalYaw;pitch=goalPitch;}
    if(frame!==lastFrame || moving || dirty){
      let i=frame*info.stride;
      const groupOffset=i+info.cards.length*13+19;
      ground.update(data,i,groupOffset);deck.userData.setPackets(data,groupOffset);
      for(let leaf=0;leaf<deck.skeleton.bones.length;leaf++) {
        const bone=deck.skeleton.bones[leaf];
        setAffine(bone.matrix,data,i);
        bone.matrixWorldNeedsUpdate=true;
        deck.userData.bends[leaf]=data[i+12];
        i+=13;
      }
      setAffine(matrix,data,i);i+=12;
      shot.setFromRotationMatrix(matrix);
      focus.setFromMatrixPosition(matrix);
      const scale=data[i++],originX=data[i++],originY=data[i++];
      center.set(data[i++],data[i++],data[i++]);
      const radius=data[i];
      const mix=clamp(Math.hypot(yaw,pitch)*1.85,0,1);
      const blend=mix*mix*(3-2*mix);
      focus.lerp(center,blend);
      orbit.setFromEuler(angles.set(pitch,yaw,0,'YXZ'));
      camera.quaternion.copy(shot).multiply(orbit);
      camera.position.set(0,0,info.distance).applyQuaternion(camera.quaternion).add(focus);
      const aspect=width/height;
      const defaultHalf=info.filmSize[1]/(2*scale);
      const safeHalf=Math.max(defaultHalf,1.065*radius*info.distance/Math.sqrt(info.distance**2-radius**2)/Math.min(1,aspect));
      const half=defaultHalf+(safeHalf-defaultHalf)*blend;
      camera.aspect=aspect;camera.fov=2*Math.atan(half/info.distance)/DEG;
      camera.clearViewOffset();
      const shiftX=(.5-originX/info.filmSize[0])*width*(1-blend);
      const shiftY=(.5-originY/info.filmSize[1])*height*(1-blend);
      camera.setViewOffset(width,height,shiftX,shiftY,width,height);
      renderer.render(scene,camera);
      lastFrame=frame;dirty=false;
    }
    if(!paused || moving)queue();
  }
  function setPaused(value) {
    if(paused===value) return;
    paused=value;previous=null;measuredTime=0;intervalCount=0;dirty=true;queue();
  }
  function dispose() {
    if(disposed)return;
    disposed=true;shown=false;abort.abort();observer.disconnect();cancelAnimationFrame(frameRequest);
    deck.geometry.dispose();deck.material.dispose();deck.customDepthMaterial.dispose();deck.skeleton.dispose();texture.dispose();
    floor.geometry.dispose();floor.material.dispose();key.shadow.dispose();
    renderer.dispose();renderer.forceContextLoss();canvas.remove();
  }
  return {
    start(still) {paused=still;shown=true;previous=null;resize();queue();},
    setPaused, dispose,
  };
}
