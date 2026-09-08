/* Pure arithmetic is exported for Node regression tests; UI stays browser-local. */
(() => {
  'use strict';
  const defaults = Object.freeze({minutes: 30, lap: 120, fuel: 3});
  function calculate(input) {
    const values = {};
    const usedDefaults = [];
    for (const key of ['minutes', 'lap', 'fuel']) {
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
      const bounds = {minutes: [1, 1440], lap: [10, 1800], fuel: [.01, 100]}[key];
      if (!Number.isFinite(number) || number < bounds[0] || number > bounds[1]) return {error: key};
      values[key] = number;
    }
    // Small tolerance avoids inventing a lap from floating-point boundary noise.
    const timedLaps = Math.ceil(values.minutes * 60 / values.lap - 1e-10);
    const plannedLaps = timedLaps + 1;
    const baseFuel = plannedLaps * values.fuel;
    const reserve = Math.max(baseFuel * .1, values.fuel);
    const totalFuel = Math.ceil((baseFuel + reserve) * 10 - 1e-9) / 10;
    return {values, usedDefaults, timedLaps, plannedLaps, baseFuel, reserve, totalFuel};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {calculate, defaults};
  if (typeof document === 'undefined') return;
  const form = document.getElementById('strategy-form');
  if (!form) return;
  const tr = (zh, en) => document.documentElement.dataset.guideLanguage === 'en' ? en : zh;
  const fields = Object.fromEntries(['minutes', 'lap', 'fuel'].map(key => [key, document.getElementById(`strategy-${key}`)]));
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
      };
      error.textContent = tr(...messages[estimate.error]);
      return false;
    }
    const number = value => value.toLocaleString(document.documentElement.dataset.guideLanguage === 'en' ? 'en-US' : 'zh-CN', {maximumFractionDigits: 2});
    const labels = {minutes: tr('比赛时长', 'Race duration'), lap: tr('平均圈速', 'Average lap time'), fuel: tr('每圈油耗', 'Fuel per lap')};
    document.getElementById('strategy-assumptions').textContent = tr(
      `本次使用：${number(estimate.values.minutes)} 分钟 · ${number(estimate.values.lap)} 秒/圈 · ${number(estimate.values.fuel)} L/圈。`,
      `Using: ${number(estimate.values.minutes)} min · ${number(estimate.values.lap)} sec/lap · ${number(estimate.values.fuel)} L/lap.`
    ) + (estimate.usedDefaults.length ? tr(' 使用默认值：', ' Defaults used: ') + estimate.usedDefaults.map(key => labels[key]).join('、') : tr(' 全部使用输入值。', ' All values supplied by you.'));
    for (const [id, value] of Object.entries({laps: estimate.plannedLaps, timed: estimate.timedLaps, base: estimate.baseFuel, reserve: estimate.reserve, total: estimate.totalFuel})) {
      document.getElementById(`strategy-${id}`).textContent = number(value);
    }
    return true;
  }
  form.addEventListener('submit', event => { event.preventDefault(); if (!render()) Object.values(fields).find(field => field.getAttribute('aria-invalid') === 'true').focus(); });
  form.addEventListener('input', render);
  form.addEventListener('reset', () => { Object.values(fields).forEach(field => { field.value = ''; }); render(); });
  document.addEventListener('gtd:languagechange', render);
  form.hidden = false;
  render();
})();
