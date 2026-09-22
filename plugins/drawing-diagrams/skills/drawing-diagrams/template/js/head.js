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
  // Empty columns still occupy explicit CSS tracks, even before the first card.
  var gs=getComputedStyle(grid),widths=gs.gridTemplateColumns.split(/\s+/).map(parseFloat),gap=parseFloat(gs.columnGap),x=parseFloat(gs.paddingLeft);
  for(var c=0;c<C;c++){var w=widths[c];if(!cols[c])cols[c]={l:x,r:x+w};x+=w+gap}
  return{cols:cols,rows:rows,C:C,R:R}}
