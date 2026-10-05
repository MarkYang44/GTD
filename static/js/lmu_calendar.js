/* Progressive enhancement only: schedule data and UK times are server-rendered. */
(() => {
  'use strict';
  const tr = (zh, en) => document.documentElement.dataset.guideLanguage === 'en' ? en : zh;
  const number = value => String(Math.round(value * 10) / 10);
  const line = (parent, text) => { const p = document.createElement('p'); p.textContent = text; parent.append(p); };
  function render() {
    document.querySelectorAll('[data-calendar-strategy]').forEach(card => {
      const target = card.querySelector('[data-calendar-result]');
      target.replaceChildren();
      const result = window.GtdLmuStrategy.calculate(JSON.parse(card.dataset.calendarStrategy));
      if (result.error) { line(target, tr('策略输入无效。', 'Invalid strategy inputs.')); return; }
      line(target, tr('估算圈数：', 'Estimated laps: ') + result.plannedLaps);
      line(target, tr('基础燃油：', 'Base fuel: ') + number(result.baseFuel) + ' L');
      for (const [key, plan] of Object.entries(result.plans)) {
        const section = document.createElement('section'); section.className = 'calendar-plan';
        const title = document.createElement('h4'); title.textContent = key === 'regular' ? tr('常规估算', 'Regular estimate') : tr('保守估算', 'Conservative estimate'); section.append(title);
        line(section, tr('总燃油 / 安全余量：', 'Total fuel / safety reserve: ') + number(plan.totalFuel) + ' / ' + number(plan.reserve) + ' L');
        if (!plan.feasible) { line(section, tr('油箱不足以完成暖胎圈与第一圈预算。', 'Tank cannot cover formation fuel and the first lap budget.')); target.append(section); continue; }
        line(section, tr('起步燃油：', 'Starting fuel: ') + number(plan.startFuel) + ' L');
        line(section, tr('预计加油进站次数：', 'Estimated refueling stops: ') + plan.stops.length);
        line(section, tr('预计进站损失：', 'Estimated pit loss: ') + number(plan.pitLoss) + ' s');
        for (const stop of plan.stops.slice(0, 20)) {
          line(section, tr('完成圈数 / 出站目标 / 预计补油：', 'After lap / exit target / estimated addition: ') + stop.afterLap + ' / ' + number(stop.targetFuel) + ' L / ' + number(stop.addFuel) + ' L');
        }
        if (plan.stops.length > 20) line(section, tr('仅显示前 20 站；合计包含全部进站。', 'Only the first 20 stops are shown; totals include every stop.'));
        target.append(section);
      }
    });
  }
  const offline = () => { document.getElementById('calendar-offline').hidden = navigator.onLine; };
  render(); offline();
  document.addEventListener('gtd:languagechange', render);
  window.addEventListener('online', offline); window.addEventListener('offline', offline);
})();
