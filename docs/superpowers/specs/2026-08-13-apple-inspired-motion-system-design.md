# Apple-Inspired Motion System Design

## Objective

Add a restrained, premium motion language across the downloader homepage, the
usage guide, and the Kozeki Ui hidden page. The result should feel polished and
spatial without becoming decorative, distracting, or slower to use.

Landing Love is used as an inspiration catalog for layered entrances, scroll
choreography, and responsive interaction feedback. No individual featured site
or animation is copied.

## Direction

Use a native CSS and JavaScript motion system. Do not add GSAP, Three.js,
WebGL, new image assets, or other runtime dependencies.

The motion language has five characteristics:

1. restrained distances and angles;
2. soft opacity and blur transitions;
3. staggered hierarchy rather than simultaneous movement;
4. subtle depth that responds to scrolling and desktop pointer movement;
5. immediate static fallbacks for reduced-motion users and touch devices.

The existing dark theme, Petronas green accent, typography, layout, content,
download behavior, and service status behavior remain unchanged.

## Shared Architecture

Create two shared assets:

- `static/css/motion.css` owns motion tokens, reveal states, pointer-light
  styling, interactive sheen, tilt transforms, and reduced-motion fallbacks.
- `static/js/motion.js` owns capability detection, reveal observation,
  animation-frame scheduling, pointer tracking, scroll-linked CSS variables,
  page visibility handling, and cleanup.

All three pages load these assets. Page-specific markup opts into behaviors
through declarative attributes and classes:

- `data-motion-reveal` for scroll entrance;
- `data-motion-group` and `data-motion-order` for stagger order;
- `data-motion-surface` for desktop sheen and micro-tilt;
- `data-motion-parallax` with a small numeric strength for scroll depth;
- `data-motion-number` for metric interpolation where the text is numeric.

The shared script must not depend on downloader-specific functions. The
homepage retains `static/js/index.js` for queue and form behavior; the motion
script only observes rendered state and DOM attributes.

## Motion Tokens

Define a small set of reusable CSS custom properties:

- fast feedback: about 160-220 ms;
- entrance: about 550-750 ms;
- stagger: about 55-90 ms;
- easing: a smooth deceleration curve similar to
  `cubic-bezier(.2, .75, .2, 1)`;
- reveal translation: no more than 18 px;
- entrance blur: no more than 8 px;
- interactive tilt: no more than approximately 0.6 degrees;
- parallax travel: normally 4-12 px;
- sheen opacity: low enough that text and controls keep their contrast.

Only `transform`, `opacity`, `filter` during finite entrances, and CSS custom
properties are animated. Pointer and scroll loops update at most once per
animation frame.

## Shared Page Entrance and Scroll Reveal

Before JavaScript enables motion, all content is fully visible. JavaScript adds
a `motion-ready` class only after initial setup, avoiding invisible content
when scripts fail or are blocked.

Reveal groups enter in visual reading order:

1. kicker or section index;
2. heading;
3. explanatory copy;
4. controls, data bands, cards, or media.

Elements enter once by default. Repeated scrolling must not replay whole page
sections. Dynamically inserted task items keep their existing short entrance
animation and are not routed through the full-page observer.

## Desktop Pointer Sheen and Micro-Tilt

Pointer effects run only when all of the following are true:

- `(hover: hover)`;
- `(pointer: fine)`;
- reduced motion is not requested;
- the document is visible.

Eligible cards and media surfaces receive a soft radial Petronas-green sheen
that follows the pointer inside the surface. A tiny perspective tilt is derived
from pointer position and clamped to the design limit. The effect returns to
neutral smoothly on pointer leave.

Interactive form controls, textareas, buttons, links, radio options, switches,
and task action controls must remain flat and readable. Applying a sheen to a
parent must not move the hit targets independently or interfere with focus,
selection, scrolling, or click handling.

Touch and coarse-pointer devices receive no pointer listeners and no tilt.

## Scroll Depth and Top Bar

Scroll-linked motion is limited to decorative layers:

- homepage hero orbit and background field;
- guide hero decoration and document background accents;
- Kozeki hero/media imagery and gallery accents.

Content text and form controls do not continuously move with scrolling. Depth
values are clamped and updated through one shared requestAnimationFrame cycle.

Each page's top bar continues its existing scrolled state, with a smoother
transition of background opacity, backdrop blur, border, and shadow. It must
not change height during scrolling, preventing layout shift.

## Homepage Behavior

The homepage adds:

- staged hero entrance;
- metric-band stagger and animated Active/Queue/Limit numbers;
- light depth movement on the decorative orbit and background only;
- desktop sheen and micro-tilt on the video card, audio card, collection
  preview, and task panel;
- subtle emphasis when queue metrics change;
- preservation of the existing task-item entrance, serial polling, form
  interactions, collection preview, folder picker, retry, cancel, and
  redownload behavior.

Metric interpolation uses the latest rendered value as its start. If updates
arrive during an animation, the current visible value becomes the next start so
the display never jumps backward. Non-numeric fallback text is rendered
immediately.

## Guide Page Behavior

The guide adds:

- staged title and introduction entrance;
- one-time reveals for document sections;
- restrained sheen/tilt on major instructional cards or panels;
- a small parallax shift for decorative background layers only;
- unchanged anchors, navigation, code samples, selection, and reading flow.

Long-form readability has priority. Paragraphs do not individually animate,
and section delays are short enough that scrolling never leaves a blank reading
area.

## Kozeki Ui Hidden Page Behavior

The hidden page adds:

- staged hero, race data, video card, and gallery entrances;
- slight desktop depth on the hero decoration and gallery media;
- a restrained sheen and micro-tilt on the main video card and gallery shots;
- unchanged external link behavior, image loading, captions, and content.

Images may scale only minimally and must remain inside their current clipping
bounds, preventing layout shift or horizontal overflow.

## Reduced Motion, Accessibility, and Failure Safety

When `prefers-reduced-motion: reduce` matches:

- all content is immediately visible;
- no scroll parallax, pointer sheen tracking, tilt, blur entrance, or number
  interpolation runs;
- existing loading spinners may continue only where necessary to communicate
  active work;
- focus, hover color, and non-motion status cues remain.

The implementation preserves semantic markup, focus order, keyboard operation,
ARIA live regions, contrast, and clickable target geometry. Motion layers use
`pointer-events: none` and cannot cover controls.

If `IntersectionObserver`, `matchMedia`, or animation-frame APIs are absent,
the page remains fully visible and functional with static styling.

## Performance and Lifecycle

Use one shared animation-frame scheduler per page rather than one loop per
element. Pointer work is scoped to the active surface. Scroll state is sampled,
then written as CSS variables in a single frame.

When the document becomes hidden:

- stop pending pointer and scroll frames;
- return active tilted surfaces to neutral;
- retain reveal completion state.

When visible again, refresh the current scroll variables once and resume only
when input occurs. No permanent timer or idle animation loop is permitted.

## Testing and Acceptance

Automated tests must verify:

- all three pages load `motion.css` and deferred `motion.js` successfully;
- opt-in attributes are present on the intended sections and surfaces;
- motion initialization is fail-open, so content is visible before setup;
- fine-pointer and reduced-motion capability gates exist;
- one requestAnimationFrame scheduler handles pointer/scroll updates;
- hidden-page lifecycle pauses work;
- metric interpolation handles updates and non-numeric values;
- existing homepage handlers and downloader behavior remain unchanged;
- JavaScript syntax, Flask surface tests, and the full Python suite pass.

Visual acceptance covers desktop and mobile widths on all three pages:

- no horizontal overflow or layout shift;
- text and controls remain crisp and usable during motion;
- desktop sheen is subtle and tracks only eligible surfaces;
- touch layouts have no tilt;
- reduced-motion mode is effectively static;
- browser console contains no errors.

## Out of Scope

- redesigning page structure, copy, typography, or colors;
- changing downloader, queue, preview, or retry behavior;
- adding WebGL, video backgrounds, third-party animation packages, or new
  artwork;
- recreating Landing Love or any featured site verbatim;
- changing the existing 8233 service configuration.
