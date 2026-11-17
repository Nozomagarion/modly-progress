const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const context = vm.createContext({});
vm.runInContext(readFileSync(require('node:path').join(__dirname, '../assets/progress.js'), 'utf8'), context);
const view = (step, progress, elapsed = 20) => context.modlyProgressView({ blockStep: step, blockProgress: progress }, elapsed);
test('loading never claims a percentage or a remaining duration', () => {
  const v = view('Loading Generate Mesh…', 5);
  assert.equal(v.percent, null);
  assert.equal(v.eta, 'Temps restant inconnu');
});
test('real diffusion steps show phase completion, not weighted backend percentage', () => {
  const v = view('Diffusion 15/30', 46);
  assert.equal(v.percent, 50);
  assert.equal(v.eta, 'Diffusion restante ≈ 20 s');
});
test('decoding does not claim that diffusion 100% means the model is done', () => {
  const v = view('Décodage du volume — durée inconnue', 82);
  assert.equal(v.percent, null);
});
test('unknown generator progress is explicitly described as possibly estimated', () => {
  const v = view('Generating 3D shape…', 55);
  assert.equal(v.percent, 55);
  assert.match(v.caption, /estimée/);
  assert.equal(v.eta, 'Temps restant inconnu');
});
test('invalid progress, bounds and zero steps remain safe', () => {
  assert.equal(view('Working', NaN).percent, null);
  assert.equal(view('Working', 500).percent, 100);
  assert.equal(view('Diffusion 0/30', 12).percent, 0);
  assert.equal(view('Diffusion 0/0', 0).eta, 'Temps restant inconnu');
});
test('remaining duration waits for enough evidence and covers only diffusion', () => {
  assert.equal(view('Diffusion 1/30', 14, 1).eta, 'Décodage et export à suivre');
  assert.equal(view('Diffusion 30/30', 80).eta, 'Décodage et export à suivre');
});
