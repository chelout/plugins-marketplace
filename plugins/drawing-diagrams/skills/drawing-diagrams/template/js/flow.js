 drawKind.flow=function(rr){var T=tracks();
  var M=Math.max(8,(+getComputedStyle(sec).getPropertyValue('--dg-padl').replace('px','')||14)-6);
  function bx(X){if(X%2===1)return (T.cols[(X-1)/2].l+T.cols[(X-1)/2].r)/2;var g=X/2;if(g===0)return T.cols[0].l-M;if(g===T.C)return T.cols[T.C-1].r+M;return (T.cols[g-1].r+T.cols[g].l)/2}
  function by(Y){if(Y%2===1)return (T.rows[(Y-1)/2].t+T.rows[(Y-1)/2].b)/2;var g=Y/2;if(g===0)return T.rows[0].t-M;if(g===T.R)return T.rows[T.R-1].b+M;return (T.rows[g-1].b+T.rows[g].t)/2}
  E.forEach(function(e){var g=document.createElementNS(NS,'g');g.setAttribute('data-e',e.a+' '+e.b);
   var pts=e.path.map(function(p){return{x:bx(p[0])+p[2],y:by(p[1])+p[3]}});
   var ca=grid.querySelector('[data-t="'+e.a+'"]').getBoundingClientRect(),cb=grid.querySelector('[data-t="'+e.b+'"]').getBoundingClientRect();
   function anchor(cr,side,nb){var l=cr.left-rr.left,r=cr.right-rr.left,t=cr.top-rr.top,b=cr.bottom-rr.top;
    if(side==='B')return{x:nb.x,y:b};if(side==='T')return{x:nb.x,y:t};if(side==='L')return{x:l,y:nb.y};return{x:r,y:nb.y}}
   function clampY(cr,y){var t=cr.top-rr.top+10,b=cr.bottom-rr.top-10;return Math.min(Math.max(y,t),b)}
   function clampX(cr,x){var l=cr.left-rr.left+12,r=cr.right-rr.left-12;return Math.min(Math.max(x,l),r)}
   var n=pts.length,hA=(e.sa==='L'||e.sa==='R'),hB=(e.sb==='L'||e.sb==='R');
   if(n===2&&hA&&hB){var t1=Math.max(ca.top,cb.top)-rr.top,b1=Math.min(ca.bottom,cb.bottom)-rr.top;if(b1-t1>16){var ym=(t1+b1)/2;pts[1].y=ym}}
   if(hA)pts[1].y=clampY(ca,pts[1].y);else pts[1].x=clampX(ca,pts[1].x);
   if(hB)pts[n-2].y=clampY(cb,pts[n-2].y);else pts[n-2].x=clampX(cb,pts[n-2].x);
   pts[0]=anchor(ca,e.sa,pts[1]);pts[n-1]=anchor(cb,e.sb,pts[n-2]);
   var d=roundPath(pts);
   var p=document.createElementNS(NS,'path');p.setAttribute('d',d);if(e.d)p.setAttribute('class','d');g.appendChild(p);
   var last=pts[pts.length-1],prev=pts[pts.length-2],dirIn=last.x===prev.x?(last.y>prev.y?'B':'T'):(last.x>prev.x?'R':'L');
   mark(g,last,dirIn,'arrow',!!e.d);
   /* label offsets (6, 3, row e.ly) are mirrored by the room check in diagrams/flow.py */
   if(e.label){var t=document.createElementNS(NS,'text'),a0=pts[0],lx,ly,anc='start';
    if(pts.length>=3){var p1=pts[1],p2=pts[2],oy=e.path[1][3]||0;if(p2.y===p1.y){var rt=p2.x>p1.x;lx=rt?p2.x-6:p2.x+6;ly=p1.y-oy-9;anc=rt?'end':'start'}else{var my=(e.ly!=null?by(e.ly):(p1.y+p2.y)/2)+4;if(e.ls==='L'){lx=p1.x-6;ly=my;anc='end'}else{lx=p1.x+6;ly=my}}}else if(e.sa==='B'){lx=a0.x+5;ly=a0.y+14}else if(e.sa==='T'){lx=a0.x+5;ly=a0.y-6}else if(e.sa==='R'){lx=a0.x+3;ly=a0.y-5}else{lx=a0.x-3;ly=a0.y-5;anc='end'}
    t.setAttribute('x',lx);t.setAttribute('y',ly);t.setAttribute('text-anchor',anc);t.textContent=e.label;g.appendChild(t)}
   svg.appendChild(g)})};
