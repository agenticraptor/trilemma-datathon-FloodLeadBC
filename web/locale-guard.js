/* FloodLead BC locale guard. Loaded before uPlot (same origin, no inline script; CSP-safe).
 * uPlot runs `new Intl.NumberFormat(navigator.language)` when its script loads. Some browsers report a
 * POSIX locale such as "en-US@posix", which is not a valid BCP 47 tag, so that call throws
 * "RangeError: Invalid language tag" and the chart library never loads. If the browser's language tag
 * is invalid, report 'en-CA' instead; if navigator.language cannot be redefined, make the Intl
 * constructors fall back to 'en-CA' for invalid tags. Does nothing for a valid language tag. */
'use strict';
(function () {
  var FALLBACK = 'en-CA';
  function valid(tag) {
    try { new Intl.NumberFormat(tag); return true; } catch (e) { return false; }
  }
  if (typeof Intl !== 'object' || typeof navigator !== 'object') return;
  var lang;
  try { lang = navigator.language; } catch (e) { lang = undefined; }
  if (valid(lang)) return;

  // 1. Redefine navigator.language / navigator.languages on the instance.
  try {
    Object.defineProperty(navigator, 'language', { configurable: true, get: function () { return FALLBACK; } });
    Object.defineProperty(navigator, 'languages', { configurable: true, get: function () { return [FALLBACK]; } });
  } catch (e) { /* already redefined as non-configurable: use step 2 */ }

  // 2. If the tag is still invalid, make Intl.NumberFormat / Intl.DateTimeFormat fall back to en-CA.
  var now;
  try { now = navigator.language; } catch (e) { now = undefined; }
  if (valid(now)) return;
  function safe(Ctor) {
    if (typeof Ctor !== 'function') return Ctor;
    var Wrapped = function (locales, options) {
      try { return new Ctor(locales, options); } catch (e) {
        if (e instanceof RangeError) return new Ctor(FALLBACK, options);
        throw e;
      }
    };
    Wrapped.prototype = Ctor.prototype;
    if (typeof Ctor.supportedLocalesOf === 'function') Wrapped.supportedLocalesOf = Ctor.supportedLocalesOf.bind(Ctor);
    return Wrapped;
  }
  try {
    Intl.NumberFormat = safe(Intl.NumberFormat);
    Intl.DateTimeFormat = safe(Intl.DateTimeFormat);
  } catch (e) { /* nothing more we can do */ }
})();
