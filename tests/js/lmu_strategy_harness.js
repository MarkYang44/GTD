'use strict';
const assert = require('node:assert/strict');
const {calculate} = require('../../static/js/lmu_strategy.js');
let r = calculate({});
assert.deepEqual(r.usedDefaults, ['minutes', 'lap', 'fuel']);
assert.equal(r.plannedLaps, 16);
assert.equal(r.totalFuel, 52.8);
r = calculate({minutes: '45', lap: '1:30', fuel: '2.6'});
assert.equal(r.timedLaps, 30);
assert.equal(r.plannedLaps, 31);
assert.equal(r.totalFuel, 88.7);
assert.deepEqual(r.usedDefaults, []);
assert.deepEqual(calculate({lap: '120'}), calculate({lap: '2:00'}));
assert.equal(calculate({minutes: '30.1'}).plannedLaps, 17);
assert.equal(calculate({minutes: '1'}).totalFuel, 9); // At least one lap of reserve.
assert.equal(calculate({minutes: '60', lap: ' ', fuel: ''}).totalFuel, 102.3);
assert.equal(calculate({lap: '1:30.500'}).values.lap, 90.5);
for (const bad of ['0', '-1', 'Infinity', 'NaN', 'x', '1e2', '0x20']) {
  for (const key of ['minutes', 'lap', 'fuel']) assert.equal(calculate({[key]: bad}).error, key);
}
for (const bad of ['1:60', '2:', ':30', '1:2', 'abc:00']) assert.equal(calculate({lap: bad}).error, 'lap');
assert.equal(calculate({minutes: '1441'}).error, 'minutes');
assert.equal(calculate({lap: '1801'}).error, 'lap');
assert.equal(calculate({fuel: '101'}).error, 'fuel');
for (let minutes = 1; minutes <= 1440; minutes += 11) {
  r = calculate({minutes, lap: '93.7', fuel: '2.73'});
  assert(r.totalFuel + 1e-9 >= r.baseFuel + r.reserve);
  assert(r.plannedLaps * r.values.lap > minutes * 60);
}
console.log('LMU strategy arithmetic checks passed');
