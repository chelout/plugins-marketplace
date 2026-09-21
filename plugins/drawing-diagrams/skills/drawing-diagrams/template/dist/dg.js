(function(){
if(window.__dgInit)return;window.__dgInit=true;
var NS='http://www.w3.org/2000/svg',DIR={R:[1,0],L:[-1,0],T:[0,-1],B:[0,1]},RAD=8;
function roundPath(pts){var q=[];pts.forEach(function(p){if(!q.length||Math.abs(q[q.length-1].x-p.x)>0.01||Math.abs(q[q.length-1].y-p.y)>0.01)q.push(p)});
 if(q.length<2)return '';var d='M'+q[0].x+' '+q[0].y;
 for(var i=1;i<q.length-1;i++){var a=q[i-1],b=q[i],c=q[i+1];var l1=Math.hypot(b.x-a.x,b.y-a.y),l2=Math.hypot(c.x-b.x,c.y-b.y);var r=Math.min(RAD,l1/2,l2/2);
  var p1={x:b.x+(a.x-b.x)/l1*r,y:b.y+(a.y-b.y)/l1*r},p2={x:b.x+(c.x-b.x)/l2*r,y:b.y+(c.y-b.y)/l2*r};
  d+='L'+p1.x+' '+p1.y+'Q'+b.x+' '+b.y+' '+p2.x+' '+p2.y}
 var z=q[q.length-1];d+='L'+z.x+' '+z.y;return d}
function init(sec){
 if(sec.getAttribute('data-init'))return;sec.setAttribute('data-init','1');
 var grid=sec.querySelector('.dg-grid'),svg=sec.querySelector('.dg-svg'),all=sec.querySelector('.dg-all'),ej=sec.querySelector('.dg-edges');
 if(!grid||!svg||!ej)return;
 var E=JSON.parse(ej.textContent||'[]');
 var L=JSON.parse(sec.getAttribute('data-labels')||'{}');var active=null,drawKind={},ready=[];
 function mark(g,P,s,kind,muted){var d=DIR[s],p=[d[1],d[0]];
  if(kind==='arrow'){var ax=P.x-d[0]*9,ay=P.y-d[1]*9,f2=document.createElementNS(NS,'path');
   f2.setAttribute('d','M'+P.x+' '+P.y+'L'+(ax+p[0]*4.5)+' '+(ay+p[1]*4.5)+'L'+(ax-p[0]*4.5)+' '+(ay-p[1]*4.5)+'Z');f2.setAttribute('class','arrow'+(muted?' m':''));g.appendChild(f2);return}
  if(kind==='one'){var c=document.createElementNS(NS,'circle');c.setAttribute('cx',P.x+d[0]*3);c.setAttribute('cy',P.y+d[1]*3);c.setAttribute('r',3.2);if(muted)c.setAttribute('class','m');g.appendChild(c)}
  else if(kind==='many'){var qx=P.x+d[0]*11,qy=P.y+d[1]*11,f=document.createElementNS(NS,'path');
   f.setAttribute('d','M'+qx+' '+qy+'L'+(P.x+p[0]*6)+' '+(P.y+p[1]*6)+'M'+qx+' '+qy+'L'+P.x+' '+P.y+'M'+qx+' '+qy+'L'+(P.x-p[0]*6)+' '+(P.y-p[1]*6));if(muted)f.setAttribute('class','m');g.appendChild(f)}}
 function tracks(){var rr=grid.getBoundingClientRect(),cols={},rows={};
  grid.querySelectorAll('.dg-c[data-r]').forEach(function(c){var r=c.getBoundingClientRect(),ci=+c.getAttribute('data-c'),ri=+c.getAttribute('data-r');
   var l=r.left-rr.left,rt=r.right-rr.left,t=r.top-rr.top,b=r.bottom-rr.top;
   cols[ci]=cols[ci]?{l:Math.min(cols[ci].l,l),r:Math.max(cols[ci].r,rt)}:{l:l,r:rt};
   rows[ri]=rows[ri]?{t:Math.min(rows[ri].t,t),b:Math.max(rows[ri].b,b)}:{t:t,b:b}});
  var C=+getComputedStyle(sec).getPropertyValue('--dg-cols'),R=0;Object.keys(rows).forEach(function(k){R=Math.max(R,+k+1)});
  for(var r=0;r<R;r++)if(!rows[r]){var up=r-1,dn=r+1;while(up>=0&&!rows[up])up--;while(dn<R&&!rows[dn])dn++;var y=(up>=0&&dn<R)?(rows[up].b+rows[dn].t)/2:(up>=0?rows[up].b+20:rows[dn].t-20);rows[r]={t:y,b:y}}
  for(var c=0;c<C;c++)if(!cols[c]){var w=cols[0]?cols[0].r-cols[0].l:100,g=+getComputedStyle(sec).getPropertyValue('--dg-gap').replace('px','');var x0=cols[0]?cols[0].l+c*(w+g):0;cols[c]={l:x0,r:x0+w}}
  return{cols:cols,rows:rows,C:C,R:R}}
 drawKind.flow=function(rr){var T=tracks();
  var M=Math.max(8,(+getComputedStyle(sec).getPropertyValue('--dg-padl').replace('px','')||14)-6);
  function bx(X){if(X%2===1)return (T.cols[(X-1)/2].l+T.cols[(X-1)/2].r)/2;var g=X/2;if(g===0)return T.cols[0].l-M;if(g===T.C)return T.cols[T.C-1].r+M;return (T.cols[g-1].r+T.cols[g].l)/2}
  function by(Y){if(Y%2===1)return (T.rows[(Y-1)/2].t+T.rows[(Y-1)/2].b)/2;var g=Y/2;if(g===0)return T.rows[0].t-M;if(g===T.R)return T.rows[T.R-1].b+M;return (T.rows[g-1].b+T.rows[g].t)/2}
  var ov={};E.forEach(function(e){var q=e.path;[[e.sa,e.a,q[0][1]],[e.sb,e.b,q[q.length-1][1]]].forEach(function(s){if(s[0]!=='L'&&s[0]!=='R')return;var c=grid.querySelector('[data-t="'+s[1]+'"]').getBoundingClientRect(),t=c.top-rr.top,b=c.bottom-rr.top,o=ov[s[2]];ov[s[2]]=o?{t:Math.max(o.t,t),b:Math.min(o.b,b)}:{t:t,b:b}})});
  function base(Y){var o=Y%2===1&&ov[Y];return o&&o.b-o.t>16?(o.t+o.b)/2:by(Y)}
  function rowY(Y,oy){var o=Y%2===1&&ov[Y],y=base(Y)+oy;return o&&o.b-o.t>=20?Math.min(Math.max(y,o.t+10),o.b-10):y}
  E.forEach(function(e){var g=document.createElementNS(NS,'g');g.setAttribute('data-e',e.a+' '+e.b);
   var pts=e.path.map(function(p){return{x:bx(p[0])+p[2],y:rowY(p[1],p[3])}});
   var ca=grid.querySelector('[data-t="'+e.a+'"]').getBoundingClientRect(),cb=grid.querySelector('[data-t="'+e.b+'"]').getBoundingClientRect();
   function anchor(cr,side,nb){var l=cr.left-rr.left,r=cr.right-rr.left,t=cr.top-rr.top,b=cr.bottom-rr.top;
    if(side==='B')return{x:nb.x,y:b};if(side==='T')return{x:nb.x,y:t};if(side==='L')return{x:l,y:nb.y};return{x:r,y:nb.y}}
   function clampY(cr,y){var t=cr.top-rr.top+10,b=cr.bottom-rr.top-10;return Math.min(Math.max(y,t),b)}
   function clampX(cr,x){var l=cr.left-rr.left+12,r=cr.right-rr.left-12;return Math.min(Math.max(x,l),r)}
   var n=pts.length,hA=(e.sa==='L'||e.sa==='R'),hB=(e.sb==='L'||e.sb==='R');
   if(hA)pts[1].y=clampY(ca,pts[1].y);else pts[1].x=clampX(ca,pts[1].x);
   if(hB)pts[n-2].y=clampY(cb,pts[n-2].y);else pts[n-2].x=clampX(cb,pts[n-2].x);
   pts[0]=anchor(ca,e.sa,pts[1]);pts[n-1]=anchor(cb,e.sb,pts[n-2]);
   var d=roundPath(pts);
   var p=document.createElementNS(NS,'path');p.setAttribute('d',d);if(e.d)p.setAttribute('class','d');g.appendChild(p);
   var last=pts[pts.length-1],prev=pts[pts.length-2],dirIn=last.x===prev.x?(last.y>prev.y?'B':'T'):(last.x>prev.x?'R':'L');
   mark(g,last,dirIn,'arrow',!!e.d);
   if(e.label){var t=document.createElementNS(NS,'text'),A=e.la,P=pts[A[0]],
    yb=A[1]==='p'?P.y:A[1]==='m'?(pts[1].y+pts[2].y)/2:base(A[2]);
    t.setAttribute('x',P.x+A[3]);t.setAttribute('y',yb+A[4]);t.setAttribute('text-anchor',A[5]);t.textContent=e.label;g.appendChild(t)}
   svg.appendChild(g)})};
 function pt(t,c,s){var rr=grid.getBoundingClientRect(),card=grid.querySelector('[data-t="'+t+'"]'),cr=card.getBoundingClientRect(),x,y;
  if(c){var r=card.querySelector('[data-c="'+c+'"]').getBoundingClientRect();y=r.top+r.height/2-rr.top}else{y=(s==='T'?cr.top:cr.bottom)-rr.top}
  x=s==='L'?cr.left-rr.left:s==='R'?cr.right-rr.left:cr.left+cr.width/2-rr.left;return{x:x,y:y}}
 drawKind.schema=function(rr){var T=tracks();
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
 function draw(){var rr=grid.getBoundingClientRect();svg.setAttribute('viewBox','0 0 '+rr.width+' '+rr.height);while(svg.firstChild)svg.removeChild(svg.firstChild);
  var k=sec.getAttribute('data-kind')==='schema'?'schema':'flow';if(drawKind[k])drawKind[k](rr)}
 grid.querySelectorAll('.dg-c').forEach(function(c){
  c.addEventListener('mouseenter',function(){if(active)return;var t=c.getAttribute('data-t');svg.querySelectorAll('g').forEach(function(g){var on=g.getAttribute('data-e').split(' ').indexOf(t)>=0;g.setAttribute('class',on?'hi':'lo')})});
  c.addEventListener('mouseleave',function(){if(active)return;svg.querySelectorAll('g').forEach(function(g){g.setAttribute('class','')})})});
 sec.querySelectorAll('.dg-route').forEach(function(btn){btn.addEventListener('click',function(){
  var was=btn.classList.contains('on');sec.querySelectorAll('.dg-route').forEach(function(b){b.classList.remove('on')});
  grid.querySelectorAll('.dg-c').forEach(function(c){c.classList.remove('lo')});svg.querySelectorAll('g').forEach(function(g){g.setAttribute('class','')});
  if(was){active=null;return}
  btn.classList.add('on');var seq=btn.getAttribute('data-nodes').split(' '),pairs={};for(var i=0;i<seq.length-1;i++)pairs[seq[i]+' '+seq[i+1]]=1;
  grid.querySelectorAll('.dg-c').forEach(function(c){if(seq.indexOf(c.getAttribute('data-t'))<0)c.classList.add('lo')});
  svg.querySelectorAll('g').forEach(function(g){g.setAttribute('class',pairs[g.getAttribute('data-e')]?'hi':'lo')});active=btn})});
 ready.forEach(function(f){f()});draw();window.addEventListener('resize',draw);if(document.fonts&&document.fonts.ready)document.fonts.ready.then(draw);setTimeout(draw,300);
}
function boot(){document.querySelectorAll('.dg').forEach(init)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
