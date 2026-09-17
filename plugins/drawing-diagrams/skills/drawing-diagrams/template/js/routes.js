 sec.querySelectorAll('.dg-route').forEach(function(btn){btn.addEventListener('click',function(){
  var was=btn.classList.contains('on');sec.querySelectorAll('.dg-route').forEach(function(b){b.classList.remove('on')});
  grid.querySelectorAll('.dg-c').forEach(function(c){c.classList.remove('lo')});svg.querySelectorAll('g').forEach(function(g){g.setAttribute('class','')});
  if(was){active=null;return}
  btn.classList.add('on');var seq=btn.getAttribute('data-nodes').split(' '),pairs={};for(var i=0;i<seq.length-1;i++)pairs[seq[i]+' '+seq[i+1]]=1;
  grid.querySelectorAll('.dg-c').forEach(function(c){if(seq.indexOf(c.getAttribute('data-t'))<0)c.classList.add('lo')});
  svg.querySelectorAll('g').forEach(function(g){g.setAttribute('class',pairs[g.getAttribute('data-e')]?'hi':'lo')});active=btn})});
