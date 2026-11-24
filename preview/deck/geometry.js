import {
  Bone, BufferGeometry, DynamicDrawUsage, Float32BufferAttribute, MeshDepthMaterial, MeshStandardMaterial,
  RGBADepthPacking, Skeleton, SkinnedMesh, Uint16BufferAttribute,
} from 'three';

// Rows follow the round card outline and subdivide the length of the paper.
// Each leaf can bow independently around its longitudinal center, including
// the paper edge and its shadow, while the deck remains one GPU draw call.
function crossSections(width) {
  const r=.045, levels=new Set();
  for(let i=0;i<=5;i++) {
    const edge=.5-r+r*Math.cos(i*Math.PI/10);
    levels.add(-edge);levels.add(edge);
  }
  for(let i=1;i<10;i++) levels.add(i/10-.5);
  return [...levels].sort((a,b)=>a-b).map(y=>{
    const dy=Math.max(0,Math.abs(y)-(.5-r));
    const x=width/2-r+Math.sqrt(Math.max(0,r*r-dy*dy));
    return {x,y};
  });
}

function addBending(material, bends) {
  material.onBeforeCompile=shader=>{
    shader.uniforms.springCurve=bends;
    shader.vertexShader='attribute float leafIndex;\nuniform float springCurve['+bends.value.length+'];\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>',`
      #include <begin_vertex>
      float curve=springCurve[int(leafIndex)];
      transformed.z+=curve*(4.*position.y*position.y-.33);
      transformed.y*=1.-.42*abs(curve);
    `).replace('#include <beginnormal_vertex>',`
      #include <beginnormal_vertex>
      float c=springCurve[int(leafIndex)];
      objectNormal=normalize(vec3(objectNormal.x,
        (objectNormal.y-8.*c*position.y*objectNormal.z)/(1.-.42*abs(c)),objectNormal.z));
    `);
  };
}

export function makeDeck(info, texture) {
  const positions=[],normals=[],uv=[],indices=[],boneIndices=[],weights=[],leaf=[];
  const parts=[];
  const rows=crossSections(info.cardWidth);
  const perimeter=[...rows.map(({x,y})=>[x,y]),...rows.slice().reverse().map(({x,y})=>[-x,y])];
  function vertex(pos, normal, region, u,v,bone) {
    const index=positions.length/3;
    positions.push(...pos);normals.push(...normal);leaf.push(bone);
    const [x,y,w,h]=region;
    uv.push((x+.5+u*(w-1))/info.atlasSize,1-(y+.5+v*(h-1))/info.atlasSize);
    boneIndices.push(bone,0,0,0);weights.push(1,0,0,0);
    return index;
  }
  const bones=info.cards.map(({face},bone)=>{
    const depth=info.stock/2;
    const sections={};
    for(const side of [1,-1]) {
      const start=indices.length;
      const normal=[0,0,side], region=info.regions[side===1?face:'back'];
      const strip=rows.map(({x,y})=>[-x,x].map(px=>vertex([px,y,side*depth],normal,region,
        .5+side*px/info.cardWidth,.5-y,bone)));
      for(let i=1;i<strip.length;i++) {
        const [a,b]=strip[i-1],[d,c]=strip[i];
        if(side===1)indices.push(a,b,c,a,c,d);
        else indices.push(a,c,b,a,d,c);
      }
      sections[side===1?'front':'back']=[start,indices.length];
    }
    const sideStart=indices.length;
    const edge=info.regions['edge-1'];
    for(let i=0;i<perimeter.length;i++) {
      const [ax,ay]=perimeter[i],[bx,by]=perimeter[(i+1)%perimeter.length];
      const len=Math.hypot(bx-ax,by-ay);
      if(len<1e-7)continue;
      const normal=[(by-ay)/len,(ax-bx)/len,0];
      const a=vertex([ax,ay,depth],normal,edge,0,0,bone);
      const b=vertex([ax,ay,-depth],normal,edge,0,1,bone);
      const c=vertex([bx,by,-depth],normal,edge,1,1,bone);
      const d=vertex([bx,by,depth],normal,edge,1,0,bone);
      indices.push(a,b,c,a,c,d);
    }
    sections.edge=[sideStart,indices.length];parts.push(sections);
    return new Bone();
  });
  const geometry=new BufferGeometry();
  geometry.setAttribute('position',new Float32BufferAttribute(positions,3));
  geometry.setAttribute('normal',new Float32BufferAttribute(normals,3));
  geometry.setAttribute('uv',new Float32BufferAttribute(uv,2));
  geometry.setAttribute('skinIndex',new Uint16BufferAttribute(boneIndices,4));
  geometry.setAttribute('skinWeight',new Float32BufferAttribute(weights,4));
  geometry.setAttribute('leafIndex',new Float32BufferAttribute(leaf,1));
  // A squared packet exposes its top, bottom and paper edges. Drawing 52
  // coplanar-looking interiors wastes fragment work and flickers at shallow angles.
  const master=Uint16Array.from(indices);
  const active=new Uint16BufferAttribute(new Uint16Array(master.length),1);
  active.setUsage(DynamicDrawUsage);geometry.setIndex(active);
  const prior=new Uint8Array(info.casterSlots);
  function setPackets(data,offset) {
    let changed=false;
    for(let i=0;i<prior.length;i++){
      const count=data[offset+i];
      if(prior[i]!==count){prior[i]=count;changed=true;}
    }
    if(!changed)return;
    let cursor=0,leaf=0;
    const copy=([start,end])=>{
      active.array.set(master.subarray(start,end),cursor);
      cursor+=end-start;
    };
    for(const count of prior){
      if(!count)break;
      copy(parts[leaf].back);copy(parts[leaf+count-1].front);
      for(let n=0;n<count;n++)copy(parts[leaf+n].edge);
      leaf+=count;
    }
    geometry.setDrawRange(0,cursor);
    active.clearUpdateRanges();active.addUpdateRange(0,cursor);active.needsUpdate=true;
  }
  const material=new MeshStandardMaterial({map:texture,roughness:.83,metalness:.015});
  const depth=new MeshDepthMaterial({depthPacking:RGBADepthPacking});
  const bends={value:new Float32Array(bones.length)};
  addBending(material,bends);addBending(depth,bends);
  const mesh=new SkinnedMesh(geometry,material);
  mesh.customDepthMaterial=depth;mesh.userData.bends=bends.value;mesh.userData.setPackets=setPackets;
  mesh.add(...bones);mesh.bind(new Skeleton(bones));
  for(const bone of bones)bone.matrixAutoUpdate=false;
  mesh.frustumCulled=false;mesh.castShadow=true;mesh.receiveShadow=true;
  return mesh;
}
