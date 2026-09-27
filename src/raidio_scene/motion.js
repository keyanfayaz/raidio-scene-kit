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
function reactionSignal(reaction, signals) {
  if (reaction === 'attack') return .25*signals.energy + .75*signals.attack;
  return ['energy','sustained'].includes(reaction) ? signals[reaction] : 0;
}
function previewSignals(energy, accentAge) {
  const baseline = Math.min(1,Math.max(0,energy));
  if (accentAge === null || accentAge < 0) return {energy:baseline,sustained:baseline,attack:0};
  function pulse(rise,decay) {
    const peakTime=rise*Math.log(1+decay/rise);
    const peak=(1-Math.exp(-peakTime/rise))*Math.exp(-peakTime/decay);
    return Math.min(1,(1-Math.exp(-accentAge/rise))*Math.exp(-accentAge/decay)/peak);
  }
  return {energy:baseline+(1-baseline)*pulse(.04,.45),
    sustained:baseline+(1-baseline)*pulse(.25,1.1),attack:Math.exp(-accentAge/.13)};
}
function ambientElements(preset, bounds, time) {
  const {x:left, y:top, width, height} = bounds, result = [];
  if (preset === 'meteors') {
    for (let lane = 0; lane < 2; lane++) {
      const age = (time + lane*4.5)%9;
      if (age >= 1.15) continue;
      const progress = age/1.15, envelope = Math.sin(Math.PI*progress);
      const headX = left + width*(.12+.40*lane+.42*progress);
      const headY = top + height*(.10+.16*lane+.48*progress);
      for (let segment = 0; segment < 6; segment++) {
        const near = segment/6;
        result.push({kind:'line',x:headX-width*.12*near,y:headY-height*.18*near,
          width:-width*.12/6,height:-height*.18/6,
          opacity:envelope*.75*(1-near)**1.8,lineWidth:1+1.1*(1-near)});
      }
      result.push({kind:'ellipse',x:headX-2,y:headY-2,width:4,height:4,opacity:envelope*.8});
      result.push({kind:'glow',x:headX-7,y:headY-7,width:14,height:14,opacity:envelope*.16});
    }
    return result;
  }
  if (preset === 'reflection') {
    for (let index = 0; index < 18; index++) {
      const seed = ((index*7919+13)%997)/997, across = ((index*139+71)%997)/997;
      const travel = (index/18+time*.012)%1, wave = Math.sin(time*.6+seed*13);
      const rippleWidth = width*(.17+seed*.24)*(1+.12*Math.sin(time*.45+index));
      const centerX = left+width*(.15+.7*across+.08*wave);
      result.push({kind:'ellipse',x:centerX-rippleWidth/2,y:top+travel*height,
        width:rippleWidth,height:1.1+seed*.9,
        opacity:Math.sin(travel*Math.PI)*(.25+.35*(.5+.5*Math.sin(time*.55+index*1.7)))});
    }
    return result;
  }
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
    else {
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
if (typeof module !== 'undefined') module.exports = {objectTransform, lightOpacity, ambientElements, advanceSceneTime, reactionSignal, previewSignals};
