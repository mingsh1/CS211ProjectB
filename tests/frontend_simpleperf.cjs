// Lightweight UI wiring test, without a phone or a running production backend.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {value: '', checked: false, textContent: '',
    replaceChildren() {}, addEventListener() {}, append() {}, setAttribute() {}});
  return elements.get(id);
};
element('mode').value = 'trace'; element('workload').value = 'W0';
const calls = [];
const sandbox = {
  window: {}, document: {getElementById: element},
  sessionStorage: {getItem: () => '', setItem() {}},
  setInterval() {}, setTimeout() {}, Option: function() {}, console,
  fetch: async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => ({eligible: false, reason: 'not profileable'})};
  }
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../backend/web/app.js'), 'utf8'), sandbox);
(async () => {
  for (const mode of ['baseline']) {
    element('simpleperf_enabled').checked = true;
    element('mode').value = mode;
    element('mode').onchange();
    assert.equal(element('simpleperf_enabled').disabled, true);
    assert.equal(element('simpleperf_enabled').checked, false);
  }
  for (const mode of ['trace']) {
    element('mode').value = mode; element('mode').onchange();
    assert.equal(element('simpleperf_enabled').disabled, false);
  }
  element('device').value = 'phone'; element('package').value = 'org.agent';
  await element('simpleperf-probe').onclick();
  assert.equal(calls.at(-1).url, '/api/devices/simpleperf-capabilities');
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), {serial:'phone', package:'org.agent'});
  assert.equal(element('simpleperf-capabilities').textContent, 'Unavailable: not profileable');
  await element('select-chatgpt').onclick();
  assert.equal(element('package').value, 'com.openai.chatgpt');
  assert.equal(calls.at(-1).url, '/api/devices/package-details');
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), {serial:'phone', package:'com.openai.chatgpt'});
  console.log('Simpleperf UI wiring passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
