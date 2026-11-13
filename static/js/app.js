const root=document.documentElement;
root.dataset.theme=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
if(localStorage.getItem('lowbw'))document.body.classList.add('low-bw');
document.addEventListener('click',e=>{
 if(e.target.closest('#themeBtn')){root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';localStorage.setItem('theme',root.dataset.theme)}
 if(e.target.closest('#bwBtn')){const on=document.body.classList.toggle('low-bw');on?localStorage.setItem('lowbw','1'):localStorage.removeItem('lowbw')}
});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
document.querySelectorAll('[data-save-offline]').forEach(el=>{try{localStorage.setItem('lastJourney',el.innerHTML)}catch(e){}});
const off=document.getElementById('offlineBox');
if(off&&!navigator.onLine){const s=localStorage.getItem('lastJourney');off.innerHTML=s?'<div class="glass"><span class="badge badge-sim">Offline: last saved journey</span>'+s+'</div>':''}
