(function(){
var b=document.querySelector('[data-menu]'),n=document.getElementById('nav');
if(b)b.addEventListener('click',function(){var o=n.classList.toggle('open');b.setAttribute('aria-expanded',o)});
var q=document.getElementById('q'),r=document.getElementById('res');
if(!q||!r)return;
var base=document.querySelector('link[rel=stylesheet][href*="assets/style.css"]').getAttribute('href').replace('assets/style.css','');
var data=[];
function norm(s){return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')}
function esc(s){return s.replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function show(){var t=norm(q.value).split(/\s+/).filter(Boolean);
var hits=t.length?data.filter(function(p){var h=norm(p.t+' '+p.d+' '+p.k+' '+p.c);return t.every(function(w){return h.indexOf(w)>-1})}):[];
r.innerHTML=hits.length?hits.map(function(p){return '<article class="card"><a href="'+p.u+'"><span class="tag">'+esc(p.c)+'</span><h3>'+esc(p.t)+'</h3><p>'+esc(p.d)+'</p></a></article>'}).join(''):(t.length?'<p>Nenhum artigo encontrado.</p>':'')}
fetch(base+'search.json').then(function(x){return x.json()}).then(function(d){data=d;var p=new URLSearchParams(location.search).get('q');if(p)q.value=p;show()});
q.addEventListener('input',show);
q.form.addEventListener('submit',function(e){e.preventDefault();show()});
})();
