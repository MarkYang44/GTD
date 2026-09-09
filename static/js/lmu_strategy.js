/* Pure arithmetic is exported for Node regression tests; UI stays browser-local. */
(() => {
  'use strict';
  const defaults = Object.freeze({minutes: 30, lap: 120, fuel: 3, tank: 100, formation: 3, rate: 2, loss: 25});
  function calculate(input) {
    const values = {};
    const usedDefaults = [];
    for (const key of Object.keys(defaults)) {
      const raw = String(input[key] ?? '').trim();
      if (!raw) {
        values[key] = defaults[key];
        usedDefaults.push(key);
        continue;
      }
      let number;
      if (key === 'lap' && raw.includes(':')) {
        const match = raw.match(/^(\d{1,2}):([0-5]\d(?:\.\d{1,3})?)$/);
        number = match ? Number(match[1]) * 60 + Number(match[2]) : NaN;
      } else {
        number = /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw) ? Number(raw) : NaN;
      }
      const bounds = {minutes: [1, 1440], lap: [10, 1800], fuel: [.01, 100], tank: [.1, 1000], formation: [0, 1000], rate: [.01, 100], loss: [0, 3600]}[key];
      if (!Number.isFinite(number) || number < bounds[0] || number > bounds[1]) return {error: key};
      values[key] = number;
    }
    // Small tolerance avoids inventing a lap from floating-point boundary noise.
    const timedLaps = Math.ceil(values.minutes * 60 / values.lap - 1e-10);
    const plannedLaps = timedLaps + 1;
    const baseFuel = plannedLaps * values.fuel;
    const plans = Object.fromEntries([['regular', .05], ['conservative', .1]].map(([name, margin]) => {
      const reserve = Math.max(baseFuel * margin, values.fuel);
      const totalFuel = Math.ceil((baseFuel + reserve + values.formation) * 10 - 1e-9) / 10;
      // Spread contingency across stints: a stop is scheduled before exhausting
      // the budget, not after driving the tank dry. Formation is charged once.
      const budgetPerLap = (totalFuel - values.formation) / plannedLaps;
      const startFuel = Math.min(values.tank, totalFuel);
      const plan = {reserve, totalFuel, budgetPerLap, startFuel, feasible: true, stops: [], pitLoss: 0};
      if (values.formation + budgetPerLap > values.tank + 1e-9) {
        plan.feasible = false;
        return [name, plan];
      }
      let remaining = startFuel - values.formation;
      for (let lap = 1; lap <= plannedLaps; lap++) {
        if (remaining + 1e-9 < budgetPerLap) {
          const addFuel = Math.min(values.tank - remaining, (plannedLaps - lap + 1) * budgetPerLap - remaining);
          const seconds = values.loss + addFuel / values.rate;
          plan.stops.push({afterLap: lap - 1, addFuel, targetFuel: remaining + addFuel, seconds});
          plan.pitLoss += seconds;
          remaining += addFuel;
        }
        remaining = Math.max(0, remaining - budgetPerLap);
      }
      return [name, plan];
    }));
    const {reserve, totalFuel} = plans.conservative;
    return {values, usedDefaults, timedLaps, plannedLaps, baseFuel, reserve, totalFuel, plans};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {calculate, defaults};
  if (typeof document === 'undefined') return;
  const form = document.getElementById('strategy-form');
  if (!form) return;
  const tr = (zh, en) => document.documentElement.dataset.guideLanguage === 'en' ? en : zh;
  const fields = Object.fromEntries(Object.keys(defaults).map(key => [key, document.getElementById(`strategy-${key}`)]));
  const result = document.getElementById('strategy-result');
  const error = document.getElementById('strategy-error');
  function render() {
    const estimate = calculate(Object.fromEntries(Object.entries(fields).map(([key, field]) => [key, field.value])));
    Object.entries(fields).forEach(([key, field]) => field.setAttribute('aria-invalid', String(estimate.error === key)));
    error.hidden = !estimate.error;
    result.hidden = !!estimate.error;
    if (estimate.error) {
      const messages = {
        minutes: ['比赛时长请输入 1–1440 分钟。', 'Enter a race duration of 1–1440 minutes.'],
        lap: ['圈速请输入 10–1800 秒，或 m:ss 格式（如 2:00）。', 'Enter a lap time of 10–1800 seconds, or m:ss (for example, 2:00).'],
        fuel: ['每圈油耗请输入 0.01–100 升。', 'Enter fuel consumption of 0.01–100 liters per lap.'],
        tank: ['油箱容量请输入 0.1–1000 升。', 'Enter a tank capacity of 0.1–1000 liters.'],
        formation: ['暖胎圈总耗油请输入 0–1000 升。', 'Enter total formation fuel of 0–1000 liters.'],
        rate: ['加油速度请输入 0.01–100 升/秒。', 'Enter a refueling rate of 0.01–100 liters/sec.'],
        loss: ['每次进站固定损失请输入 0–3600 秒。', 'Enter a fixed pit loss of 0–3600 seconds per stop.'],
      };
      error.textContent = tr(...messages[estimate.error]);
      return false;
    }
    const number = value => value.toLocaleString(document.documentElement.dataset.guideLanguage === 'en' ? 'en-US' : 'zh-CN', {maximumFractionDigits: 2});
    const labels = {minutes: tr('比赛时长', 'Race duration'), lap: tr('平均圈速', 'Average lap time'), fuel: tr('每圈油耗', 'Fuel per lap'), tank: tr('油箱容量', 'Tank capacity'), formation: tr('暖胎圈耗油', 'Formation fuel'), rate: tr('加油速度', 'Refueling rate'), loss: tr('固定进站损失', 'Fixed pit loss')};
    document.getElementById('strategy-assumptions').textContent = tr(
      `本次使用：${number(estimate.values.minutes)} 分钟 · ${number(estimate.values.lap)} 秒/圈 · ${number(estimate.values.fuel)} L/圈；油箱 ${number(estimate.values.tank)} L，暖胎圈 ${number(estimate.values.formation)} L，加油 ${number(estimate.values.rate)} L/秒，固定损失 ${number(estimate.values.loss)} 秒/次。`,
      `Using: ${number(estimate.values.minutes)} min · ${number(estimate.values.lap)} sec/lap · ${number(estimate.values.fuel)} L/lap; tank ${number(estimate.values.tank)} L, formation ${number(estimate.values.formation)} L, refueling ${number(estimate.values.rate)} L/sec, fixed loss ${number(estimate.values.loss)} sec/stop.`
    ) + (estimate.usedDefaults.length ? tr(' 使用默认值：', ' Defaults used: ') + estimate.usedDefaults.map(key => labels[key]).join(tr('、', ', ')) : tr(' 全部使用输入值。', ' All values supplied by you.'));
    for (const [id, value] of Object.entries({laps: estimate.plannedLaps, timed: estimate.timedLaps, base: estimate.baseFuel, reserve: estimate.reserve, total: estimate.totalFuel})) {
      document.getElementById(`strategy-${id}`).textContent = number(value);
    }
    for (const [name, plan] of Object.entries(estimate.plans)) {
      const card = document.getElementById(`strategy-${name}`);
      const set = (field, text) => { card.querySelector(`[data-plan="${field}"]`).textContent = text; };
      set('total', number(plan.totalFuel));
      set('reserve', number(plan.reserve));
      set('budget', number(plan.budgetPerLap));
      set('start', plan.feasible ? number(plan.startFuel) : '—');
      set('stops', plan.feasible ? number(plan.stops.length) : '—');
      set('loss', plan.feasible ? number(plan.pitLoss) : '—');
      set('status', !plan.feasible
        ? tr('油箱无法容纳暖胎圈及第一圈的燃油预算，请核对容量与耗油。', 'The tank cannot cover formation fuel plus the first budgeted lap. Check capacity and consumption.')
        : plan.stops.length ? tr('需要进站加油；以下圈次按含安全余量的油耗规划。', 'Refueling required. Stop laps use the fuel budget including reserve.')
        : tr('燃油预算可一箱完成；赛事强制进站要求需另外核对。', 'One tank covers the fuel budget. Check mandatory event stops separately.'));
      const schedule = card.querySelector('[data-plan-schedule]');
      schedule.hidden = !plan.feasible || !plan.stops.length;
      const rows = card.querySelector('tbody');
      rows.replaceChildren();
      plan.stops.slice(0, 20).forEach((stop, index) => {
        const row = document.createElement('tr');
        for (const value of [index + 1, stop.afterLap, stop.targetFuel, stop.addFuel, stop.seconds]) {
          const cell = document.createElement('td');
          cell.textContent = number(value);
          row.append(cell);
        }
        rows.append(row);
      });
      set('truncated', plan.stops.length > 20 ? tr('仅列出前 20 次进站，合计包含全部进站。', 'Only the first 20 stops are listed; totals include every stop.') : '');
    }
    return true;
  }
  form.addEventListener('submit', event => { event.preventDefault(); if (!render()) { const field = Object.values(fields).find(field => field.getAttribute('aria-invalid') === 'true'); const details = field.closest('details'); if (details) details.open = true; field.focus(); } });
  form.addEventListener('input', render);
  form.addEventListener('reset', () => { Object.values(fields).forEach(field => { field.value = ''; }); render(); });
  document.addEventListener('gtd:languagechange', render);
  form.hidden = false;
  render();
})();
