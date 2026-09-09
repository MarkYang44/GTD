'use strict';
const assert = require('node:assert/strict');
const {calculate} = require('../../static/js/lmu_strategy.js');
let r = calculate({});
assert.deepEqual(r.usedDefaults, ['minutes', 'lap', 'fuel', 'tank', 'formation', 'rate', 'loss']);
assert.equal(r.plannedLaps, 16);
assert.equal(r.totalFuel, 55.8);
r = calculate({minutes: '45', lap: '1:30', fuel: '2.6'});
assert.equal(r.timedLaps, 30);
assert.equal(r.plannedLaps, 31);
assert.equal(r.totalFuel, 91.7);
assert.deepEqual(r.usedDefaults, ['tank', 'formation', 'rate', 'loss']);
assert.deepEqual(calculate({lap: '120'}), calculate({lap: '2:00'}));
assert.equal(calculate({minutes: '30.1'}).plannedLaps, 17);
assert.equal(calculate({minutes: '1'}).totalFuel, 12); // At least one lap of reserve.
assert.equal(calculate({minutes: '60', lap: ' ', fuel: ''}).totalFuel, 105.3);
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

// Advanced defaults are assumptions, not car specifications.
r = calculate({});
assert.equal(r.plans.regular.totalFuel, 54);
assert.equal(r.plans.conservative.totalFuel, 55.8);
assert.equal(r.plans.regular.stops.length, 0);
assert.equal(r.plans.conservative.startFuel, 55.8);
const advanced = {minutes: 30, lap: 120, fuel: 3, tank: 30, formation: 0, rate: 2, loss: 25};
r = calculate(advanced).plans.conservative;
assert.equal(r.stops.length, 1);
assert.equal(r.stops[0].afterLap, 9);
assert(Math.abs(r.stops[0].addFuel - 22.8) < 1e-9);
assert(Math.abs(r.pitLoss - 36.4) < 1e-9);
assert.equal(calculate({...advanced, tank: 52.8}).plans.conservative.stops.length, 0);
assert.equal(calculate({...advanced, tank: 52.7}).plans.conservative.stops.length, 1);
assert.equal(calculate({...advanced, tank: 3}).plans.conservative.feasible, false);
assert.equal(calculate({...advanced, tank: 6, formation: 3}).plans.conservative.feasible, false);
assert.equal(calculate({...advanced, tank: 6.3, formation: 3}).plans.conservative.feasible, true);
assert.equal(calculate({...advanced, loss: 0}).plans.conservative.pitLoss, 11.4);
for (const key of ['formation', 'loss']) assert.equal(calculate({[key]: 0}).error, undefined);
for (const key of ['tank', 'rate']) assert.equal(calculate({[key]: 0}).error, key);
for (const [key, value] of Object.entries({tank: 1001, formation: 1001, rate: 101, loss: 3601})) assert.equal(calculate({[key]: value}).error, key);
for (const key of ['tank', 'formation', 'rate', 'loss']) {
  for (const bad of ['-1', 'NaN', 'Infinity', '1e2', 'abc']) assert.equal(calculate({[key]: bad}).error, key);
}
// Fuel conservation and capacity for both scenarios, including fractional tanks.
for (const minutes of [1, 30, 61, 1440]) for (const tank of [3, 6.3, 10, 30.17, 100]) {
  const estimate = calculate({...advanced, minutes, tank, formation: 1.7});
  for (const plan of Object.values(estimate.plans)) {
    if (!plan.feasible) continue;
    let remaining = plan.startFuel - 1.7;
    let added = plan.startFuel;
    let previousLap = 0;
    for (const stop of plan.stops) {
      assert(stop.afterLap > previousLap && stop.afterLap < estimate.plannedLaps);
      remaining -= (stop.afterLap - previousLap) * plan.budgetPerLap;
      assert(remaining >= -1e-8);
      assert(stop.addFuel > 0);
      remaining += stop.addFuel;
      assert(remaining <= tank + 1e-8);
      added += stop.addFuel;
      previousLap = stop.afterLap;
    }
    remaining -= (estimate.plannedLaps - previousLap) * plan.budgetPerLap;
    assert(Math.abs(remaining) < 1e-7);
    assert(Math.abs(added - plan.totalFuel) < 1e-7);
    assert(plan.totalFuel >= estimate.baseFuel + plan.reserve + 1.7 - 1e-9);
  }
}
console.log('Advanced fuel planning checks passed');

// Targets are safe even when measured burn is lower than the contingency model.
r = calculate({...advanced, minutes: 60}).plans.conservative;
assert.equal(r.stops[0].targetFuel, 30);
assert(Math.abs(r.budgetPerLap - 3.3) < 1e-9);
let actualFuel = r.startFuel;
let actualLap = 0;
for (const stop of r.stops) {
  actualFuel -= (stop.afterLap - actualLap) * 3;
  assert(actualFuel >= 0);
  const actualAdd = Math.max(0, stop.targetFuel - actualFuel);
  actualFuel += actualAdd;
  assert(actualFuel <= 30 + 1e-9);
  actualLap = stop.afterLap;
}
assert(actualFuel - (31 - actualLap) * 3 >= -1e-9);
