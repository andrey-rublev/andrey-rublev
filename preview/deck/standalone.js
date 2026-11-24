(() => {
  const view=document.getElementById('deck-film');
  const image=view.querySelector('picture img');
  const button=view.querySelector('[data-film-motion]');
  const preference=matchMedia('(prefers-reduced-motion: reduce)');
  const inspector=makeInspector(view,update);
  let still=false;

  function update(){
    const quiet=preference.matches || still;
    button.textContent=quiet?'Enable motion':'Show still';
    button.setAttribute('aria-pressed',String(quiet));
    button.hidden=preference.matches;
    inspector.setPaused(quiet);
    if(!inspector.active){
      const uri=quiet?image.dataset.still:image.dataset.film;
      if(image.getAttribute('src')!==uri)image.src=uri;
    }
  }
  button.addEventListener('click',()=>{still=!still;update()});
  preference.addEventListener('change',update);
  window.addEventListener('pagehide',()=>inspector.stop());
  window.addEventListener('pageshow',e=>{if(e.persisted){update();inspector.open();}});
  update();inspector.open();
})();