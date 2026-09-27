// Fixed toolkit renderer math, never supplied by an imported package.
function objectTransform(layer, width, height, elapsed) {
  const sx = width * layer.width, sy = height * layer.height;
  let x = width * layer.x + sx * layer.anchorX;
  let y = height * layer.y + sy * layer.anchorY;
  let a = sx, b = 0, c = 0, d = sy;
  const t = elapsed * layer.speed + layer.phase;
  if (layer.kind === 'object') {
    if (layer.preset === 'rotate') {
      a = sx * Math.cos(t); b = sy * Math.sin(t);
      c = -sx * Math.sin(t); d = sy * Math.cos(t);
    } else if (layer.preset === 'sway') {
      const angle = layer.amplitude * Math.sin(t);
      a = sx * Math.cos(angle); b = sx * Math.sin(angle);
      c = -sy * Math.sin(angle); d = sy * Math.cos(angle);
    } else if (layer.preset === 'cloth') c = sy * layer.amplitude * Math.sin(t);
    else if (layer.preset === 'drift') {
      x += width * layer.amplitude * Math.sin(t);
      y += height * layer.amplitude * 0.35 * Math.sin(t * 0.73);
    } else if (layer.preset === 'flame') d *= 1 + layer.amplitude * Math.sin(t * 3);
  }
  return [a, b, c, d, x - a * layer.anchorX - c * layer.anchorY,
    y - b * layer.anchorX - d * layer.anchorY];
}
function lightOpacity(opacity, strength, signal) {
  return Math.min(1, Math.max(0, opacity + strength * signal * (1 - opacity)));
}
function ambientElements(preset, bounds, time) {
  const {x:left, y:top, width, height} = bounds, result = [];
  if (['mist', 'steam'].includes(preset)) {
    for (let index = 0; index < 8; index++) {
      const seed = index * 2.399;
      const x = left + width*.5 + Math.sin(time*.08 + seed)*width*.35;
      const y = top + height*.5 + Math.cos(time*.05 + seed)*height*.22;
      result.push({kind:'glow', x:x-width*.38, y:y-height*.32,
        width:width*.76, height:height*.64, opacity:.14});
    }
    return result;
  }
  for (let index = 0; index < (preset === 'rain' ? 88 : 40); index++) {
    const seed = ((index*7919 + 13)%997)/997;
    const travel = (seed + time*(preset === 'rain' ? .23 : .014))%1;
    const x = left + ((index*139 + 71)%997)/997*width + Math.sin(time*.2 + seed*13)*3;
    const y = top + travel*height, alpha = Math.sin(travel*Math.PI);
    if (preset === 'rain') result.push({kind:'line',x,y,width:-1.5,height:10+seed*18,opacity:alpha*.24,lineWidth:.8});
    else if (preset === 'reflection') {
      const wave = Math.sin(time*1.5 + index*1.8);
      result.push({kind:'ellipse',x:x+wave*2,y,width:3+(wave+1)*4,height:1.5,opacity:alpha*(.25+(wave+1)*.15)});
    } else {
      const radius = preset === 'stars' ? 1.3 : 1.8;
      const particleY = preset === 'stars' ? top+seed*height : top+height-travel*height;
      const opacity = preset === 'stars' ? .35+.15*Math.sin(time*.4+seed*12) : alpha*.4;
      result.push({kind:'ellipse',x,y:particleY,width:radius*2,height:radius*2,opacity});
    }
  }
  return result;
}
function advanceSceneTime(elapsed, delta, state) {
  return state.animate && !state.paused && !state.reduce && !state.hidden && !state.poster
    ? elapsed + delta : elapsed;
}
if (typeof module !== 'undefined') module.exports = {objectTransform, lightOpacity, ambientElements, advanceSceneTime};
