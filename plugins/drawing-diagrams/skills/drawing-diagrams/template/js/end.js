 ready.forEach(function(f){f()});draw();window.addEventListener('resize',draw);if(document.fonts&&document.fonts.ready)document.fonts.ready.then(draw);setTimeout(draw,300);
}
function boot(){document.querySelectorAll('.dg').forEach(init)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
