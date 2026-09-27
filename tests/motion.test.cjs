const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {objectTransform, lightOpacity, ambientElements, advanceSceneTime, reactionSignal, previewSignals} = require('../src/raidio_scene/motion.js');
const cases = JSON.parse(readFileSync(join(__dirname, '../examples/motion-conformance.json'))).cases;

test('browser transform agrees with every Python and Swift conformance fixture', () => {
  for (const item of cases) {
    const actual = objectTransform(item.layer, item.width, item.height, item.elapsed);
    actual.forEach((value, index) => {
      assert.ok(Math.abs(value - item.affine[index]) < 1e-10, `${item.name}[${index}]`);
    });
  }
});
test('baseline light and bounded energy use the same mapping', () => {
  assert.equal(lightOpacity(.1, .2, 0), .1);
  assert.ok(Math.abs(lightOpacity(.1, .2, .5) - .19) < 1e-12);
  assert.equal(lightOpacity(.9, 1, 1), 1);
});
test('packaged preview JavaScript parses and uses the reference transform', () => {
  const html = readFileSync(join(__dirname, '../src/raidio_scene/preview.html'), 'utf8');
  const code = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1]
    .replace('__MOTION_CODE__', readFileSync(join(__dirname, '../src/raidio_scene/motion.js'), 'utf8'));
  assert.doesNotThrow(() => new Function(code));
  assert.ok(code.includes('objectTransform(layer,width,height,time)'));
});
test('browser atmosphere matches every native/Python sampled primitive', () => {
  const fixtures = JSON.parse(readFileSync(join(__dirname, '../examples/ambient-conformance.json'))).cases;
  for (const item of fixtures) {
    const actual = ambientElements(item.preset, item.bounds, item.time);
    assert.equal(actual.length, item.count);
    for (const sample of item.samples) {
      assert.equal(actual[sample.index].kind, sample.element.kind);
      for (const [key, expected] of Object.entries(sample.element)) {
        if (key !== 'kind') assert.ok(Math.abs(actual[sample.index][key] - expected) < 1e-10, `${item.preset}.${key}`);
      }
    }
  }
});
test('pause, animation-off, hiding and poster fallback freeze the existing phase', () => {
  const state = {animate:true,paused:false,reduce:false,hidden:false,poster:false};
  assert.equal(advanceSceneTime(7,.1,state),7.1);
  for (const disabled of [{animate:false},{paused:true},{reduce:true},{hidden:true},{poster:true}]) {
    assert.equal(advanceSceneTime(7,.1,{...state,...disabled}),7);
  }
});
test('all reaction channels and simulated accents match canonical fixtures', () => {
  const fixture = JSON.parse(readFileSync(join(__dirname, '../examples/reaction-conformance.json')));
  for (const item of fixture.cases) {
    assert.ok(Math.abs(reactionSignal(item.reaction,item.signals)-item.expected) < 1e-12);
  }
  for (const item of fixture.previewCases) {
    const actual=previewSignals(item.energy,item.age);
    for (const channel of ['energy','attack','sustained']) {
      assert.ok(Math.abs(actual[channel]-item.signals[channel]) < 1e-12);
    }
  }
});
test('test accent is visible for every light mapping and attack keeps full-energy headroom', () => {
  const before=previewSignals(.35,null), after=previewSignals(.35,.1);
  for (const channel of ['energy','attack','sustained']) {
    assert.ok(reactionSignal(channel,after)>reactionSignal(channel,before)+.2);
  }
  assert.equal(reactionSignal('attack',previewSignals(1,null)),.25);
  assert.equal(reactionSignal('attack',previewSignals(1,0)),1);
  assert.equal(reactionSignal('energy',previewSignals(1,0)),1);
  assert.equal(reactionSignal('none',previewSignals(1,0)),0);
});
