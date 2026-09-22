 function pt(t,c,s){var card=grid.querySelector('[data-t="'+t+'"]'),cr=box(card),x,y;
  if(c){var r=box(card.querySelector('[data-c="'+c+'"]'));y=(r.top+r.bottom)/2}else{y=s==='T'?cr.top:cr.bottom}
  x=s==='L'?cr.left:s==='R'?cr.right:(cr.left+cr.right)/2;return{x:x,y:y}}
 drawKind.schema=function(){var T=tracks();
  var M=Math.max(8,(+getComputedStyle(sec).getPropertyValue('--dg-padl').replace('px','')||14)-6);
  function gx(c,side){if(side==='R')return c+1<T.C?(T.cols[c].r+T.cols[c+1].l)/2:T.cols[c].r+M;return c>0?(T.cols[c-1].r+T.cols[c].l)/2:T.cols[c].l-M}
  E.forEach(function(e){var A=pt.apply(null,e.a),B=pt.apply(null,e.b),g=document.createElementNS(NS,'g'),off=e.off||0,d;g.setAttribute('data-e',e.a[0]+' '+e.b[0]);
   var ca=+grid.querySelector('[data-t="'+e.a[0]+'"]').getAttribute('data-c'),pts;
   if(e.via==='R'){var X=T.cols[T.C-1].r+M+off;pts=[A,{x:X,y:A.y},{x:X,y:B.y},B]}
   else if(e.via==='L'){var X2=T.cols[0].l-M+off;pts=[A,{x:X2,y:A.y},{x:X2,y:B.y},B]}
   else if(e.via==='GR'||e.via==='GL'){var X3=gx(ca,e.via[1])+off;pts=[A,{x:X3,y:A.y},{x:X3,y:B.y},B]}
   else if(e.a[2]==='T'||e.a[2]==='B'){var my=(A.y+B.y)/2+off;pts=[A,{x:A.x,y:my},{x:B.x,y:my},B]}
   else{var mx=(A.x+B.x)/2+off;pts=[A,{x:mx,y:A.y},{x:mx,y:B.y},B]}
   d=roundPath(pts);
   var p=document.createElementNS(NS,'path');p.setAttribute('d',d);if(e.d)p.setAttribute('class','d');g.appendChild(p);
   mark(g,A,e.a[2],e.ae,!!e.d);mark(g,B,e.b[2],e.be,!!e.d);svg.appendChild(g)})};
 function setOpen(card,open){card.classList.toggle('open',open);var b=card.querySelector('.dg-toggle');if(b)b.querySelector('span').textContent=open?L.collapse:b.getAttribute('data-more')}
 function syncAll(){var cards=grid.querySelectorAll('.dg-c'),anyClosed=Array.prototype.some.call(cards,function(c){return !c.classList.contains('open')});if(all)all.textContent=anyClosed?L.open_all:L.close_all;return anyClosed}
 grid.querySelectorAll('.dg-toggle').forEach(function(b){b.addEventListener('click',function(ev){ev.stopPropagation();var c=b.closest('.dg-c');setOpen(c,!c.classList.contains('open'));syncAll();draw()})});
 if(all)all.addEventListener('click',function(){var open=syncAll();grid.querySelectorAll('.dg-c').forEach(function(c){setOpen(c,open)});syncAll();draw()});
 ready.push(syncAll);
