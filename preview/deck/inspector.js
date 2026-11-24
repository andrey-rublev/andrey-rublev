function makeInspector(dialog, restoreFilm) {
  const stage=dialog.querySelector('.deck-stage');
  const tools=dialog.querySelector('.deck-orbit');
  let instance=null, sequence=0, quiet=false, cached=null;
  function loadRuntime() {
    if (!window.DeckExplorer) {
      const program=document.createElement('script');
      program.textContent=document.getElementById('deck-program').textContent;
      document.head.append(program);program.remove();
    }
    cached ||= JSON.parse(document.getElementById('deck-packet').textContent);
  }
  function stop() {
    sequence++;
    const old=instance;
    instance=null;stage.classList.remove('interactive');tools.hidden=true;
    old?.dispose();
  }
  function fallback() {
    stop();
    if(!dialog.matches('dialog:not([open])')) restoreFilm();
  }
  return {
    get active() {return !!instance;},
    setPaused(value) {quiet=value;instance?.setPaused(value);},
    async open() {
      const ticket=++sequence;
      try {
        loadRuntime();
        const next=await window.DeckExplorer.mount(stage,tools,cached,fallback);
        if(!next) return;
        if(ticket!==sequence || dialog.matches('dialog:not([open])')) {next.dispose();return;}
        instance=next;
        stage.classList.add('interactive');
        tools.hidden=false;
        next.start(quiet);
        stage.querySelector('source').removeAttribute('srcset');
        stage.querySelector('img').removeAttribute('src');
      } catch (error) {
        if(ticket===sequence) fallback();
      }
    },
    stop,
  };
}
