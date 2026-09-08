/* Animate native disclosures without changing their keyboard or no-JS behavior. */
(() => {
  'use strict';
  if (!Element.prototype.animate || !window.matchMedia) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finishers = [];

  document.querySelectorAll('details[data-recommendations]').forEach(details => {
    const summary = details.querySelector('summary');
    const content = details.querySelector('.recommendation-content');
    if (!summary || !content) return;
    let expanded = details.open;
    let animation = null;

    function finish() {
      const previous = animation;
      animation = null;
      details.open = expanded;
      content.inert = !expanded;
      summary.setAttribute('aria-expanded', String(expanded));
      previous?.cancel();
    }

    summary.addEventListener('click', event => {
      event.preventDefault();
      const start = details.open ? content.getBoundingClientRect().height : 0;
      expanded = !expanded;
      animation?.cancel();
      animation = null;
      summary.setAttribute('aria-expanded', String(expanded));
      // Keep native content displayed until the closing animation completes.
      details.open = true;
      content.inert = !expanded;
      if (!expanded && content.contains(document.activeElement)) summary.focus();
      const end = expanded ? content.scrollHeight : 0;
      if (reduced.matches || Math.abs(end - start) < 1) {
        finish();
        return;
      }
      try {
        const run = content.animate(
          [{height: `${start}px`}, {height: `${end}px`}],
          {duration: 260, easing: 'cubic-bezier(.2, .7, .2, 1)', fill: 'both'},
        );
        animation = run;
        run.onfinish = () => { if (animation === run) finish(); };
      } catch (_) {
        finish();
      }
    });
    finishers.push(() => { if (animation) finish(); });
  });

  // Return to intrinsic height if text or available width changes mid-transition.
  const finishAll = () => finishers.forEach(finish => finish());
  window.addEventListener('resize', finishAll, {passive: true});
  document.addEventListener('gtd:languagechange', finishAll);
  document.addEventListener('gtd:lmu-filterchange', finishAll);
  reduced.addEventListener?.('change', finishAll);
  document.addEventListener('visibilitychange', () => { if (document.hidden) finishAll(); });
})();
