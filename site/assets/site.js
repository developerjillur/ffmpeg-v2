const announce=document.querySelector('#announce');
function say(message){if(announce)announce.textContent=message;}
for(const pre of document.querySelectorAll('pre')){
  if(pre.querySelector('code.language-mermaid'))continue;
  const button=document.createElement('button');
  button.type='button';button.className='copy';button.textContent='Copy';
  button.setAttribute('aria-label','Copy code');
  button.addEventListener('click',async()=>{
    const value=pre.querySelector('code')?.textContent??'';
    try{await navigator.clipboard.writeText(value);button.textContent='Copied';say('Code copied to clipboard.');}
    catch{button.textContent='Select code';say('Clipboard unavailable. Select the code and copy it manually.');}
    setTimeout(()=>{button.textContent='Copy';},2200);
  });pre.append(button);
}
for(const scope of document.querySelectorAll('[data-scope]')){
  scope.addEventListener('click',()=>{
    const value=scope.dataset.scope;
    document.querySelectorAll('[data-scope]').forEach(b=>b.setAttribute('aria-pressed',String(b===scope)));
    document.querySelectorAll('[data-result]').forEach(p=>{p.hidden=value!=='all'&&p.dataset.result!==value;});
    say(value==='all'?'Showing complete workflow and direct results.':`Showing ${value} results. Other results remain available with Show all.`);
  });
}
const search=document.querySelector('#report-search');
search?.addEventListener('input',()=>{
  let shown=0;const needle=search.value.toLocaleLowerCase().trim();
  for(const item of document.querySelectorAll('.report-item')){item.hidden=!item.textContent.toLocaleLowerCase().includes(needle);if(!item.hidden)shown++;}
  const count=document.querySelector('#report-count');if(count)count.textContent=`${shown} reports shown`;
});
