 function draw(){var rr=grid.getBoundingClientRect();svg.setAttribute('viewBox','0 0 '+rr.width+' '+rr.height);while(svg.firstChild)svg.removeChild(svg.firstChild);
  var k=sec.getAttribute('data-kind')==='schema'?'schema':'flow';if(drawKind[k])drawKind[k](rr)}
 grid.querySelectorAll('.dg-c').forEach(function(c){
  c.addEventListener('mouseenter',function(){if(active)return;var t=c.getAttribute('data-t');svg.querySelectorAll('g').forEach(function(g){var on=g.getAttribute('data-e').split(' ').indexOf(t)>=0;g.setAttribute('class',on?'hi':'lo')})});
  c.addEventListener('mouseleave',function(){if(active)return;svg.querySelectorAll('g').forEach(function(g){g.setAttribute('class','')})})});
