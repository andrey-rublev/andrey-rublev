import {Mesh, PlaneGeometry, ShaderMaterial, Vector2, Vector4} from 'three';

const TABLE = -.233;

// Project each rigid packet along the key light onto the table. Blur both
// opposing edges according to height, so a thin edge casts less light loss
// than a broad face, and a card lifted from the table casts a softer shadow.
export function makeShadows(n, width, stock) {
  const slabs=Array.from({length:n},()=>new Vector4());
  const normals=Array.from({length:n},()=>new Vector4());
  const supports=Array.from({length:n},()=>new Vector2());
  const material=new ShaderMaterial({
    transparent:true,depthWrite:false,
    uniforms:{slabs:{value:slabs},normals:{value:normals},supports:{value:supports}},
    vertexShader:`
      varying vec2 onTable;
      void main(){
        onTable=position.xy;
        gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);
      }`,
    fragmentShader:`
      uniform vec4 slabs[${n}];
      uniform vec4 normals[${n}];
      uniform vec2 supports[${n}];
      varying vec2 onTable;
      float band(float x,float halfLength,float blur){
        return smoothstep(-blur,blur,x+halfLength)-smoothstep(-blur,blur,x-halfLength);
      }
      void main(){
        float loss=0.;
        for(int i=0;i<${n};i++){
          vec2 delta=onTable-slabs[i].xy;
          float radius=slabs[i].z;
          float a=band(dot(normals[i].xy,delta),supports[i].x,radius);
          float b=band(dot(normals[i].zw,delta),supports[i].y,radius);
          float strength=a*b*slabs[i].w;
          loss=max(loss,strength)+.14*min(loss,strength);
        }
        gl_FragColor=vec4(.23,.21,.18,min(.33,loss));
      }`,
  });
  const mesh=new Mesh(new PlaneGeometry(18,18),material);
  mesh.position.z=TABLE;
  const kx=-.37,ky=.43;
  function update(data,offset,groups) {
    let leaf=0;
    for(let index=0;index<n;index++) {
      const count=data[groups+index];
      if(!count){slabs[index].set(0,0,.1,0);continue;}
      const i=offset+leaf*13, j=i+(count-1)*13;
      const cx=(data[i+3]+data[j+3])*.5,cy=(data[i+7]+data[j+7])*.5;
      const z=Math.max(0,(data[i+11]+data[j+11])*.5-TABLE);
      const thickness=count*stock/2+.36*Math.abs(data[i+12]);
      leaf+=count;
      const x1=(data[i]-kx*data[i+8])*width/2;
      const y1=(data[i+4]-ky*data[i+8])*width/2;
      const x2=(data[i+1]-kx*data[i+9])*.5;
      const y2=(data[i+5]-ky*data[i+9])*.5;
      const x3=(data[i+2]-kx*data[i+10])*thickness;
      const y3=(data[i+6]-ky*data[i+10])*thickness;
      const l1=Math.max(.00001,Math.hypot(x1,y1)), l2=Math.max(.00001,Math.hypot(x2,y2));
      const ax=-y2/l2, ay=x2/l2, bx=-y1/l1, by=x1/l1;
      normals[index].set(ax,ay,bx,by);
      supports[index].set(Math.abs(ax*x1+ay*y1)+Math.abs(ax*x3+ay*y3),
                          Math.abs(bx*x2+by*y2)+Math.abs(bx*x3+by*y3));
      const strength=(count>1 ? .24:.17)/(1+.75*z);
      slabs[index].set(cx-kx*z,cy-ky*z,.028+.21*z,strength);
    }
    material.uniformsNeedUpdate=true;
  }
  return {mesh,update};
}
