// Site-wide motion: scroll-reveal (sections shift into view) + background parallax.
// Respects prefers-reduced-motion; degrades to a static page without JS.

(function () {
  "use strict";

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  // ---- reveal on scroll ----
  var selectors = [
    ".hero .eyebrow",
    ".hero h1",
    ".hero .lead",
    ".hero .cta-row",
    ".hero-stats",
    ".hero-art",
    ".module",
    ".ext-band",
    ".grid .card",
    ".doc-card",
    ".plan",
  ];
  var targets = Array.prototype.slice.call(document.querySelectorAll(selectors.join(",")));

  targets.forEach(function (el) {
    el.classList.add("reveal");
    // Stagger siblings that reveal together (cards in a grid, doc cards…).
    var siblings = Array.prototype.slice.call(el.parentElement.children).filter(function (s) {
      return s.classList && s.classList.contains("reveal");
    });
    var index = siblings.indexOf(el);
    if (index > 0) el.style.transitionDelay = Math.min(index * 90, 450) + "ms";
  });

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
    );
    targets.forEach(function (el) {
      observer.observe(el);
    });
  } else {
    targets.forEach(function (el) {
      el.classList.add("revealed");
    });
  }

  // ---- background parallax + the scroll-driven journey ----
  var journey = document.querySelector(".journey");
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      var root = document.documentElement;
      root.style.setProperty("--sy", String(window.scrollY));
      var travel = root.scrollHeight - window.innerHeight;
      var progress = travel > 0 ? Math.min(1, Math.max(0, window.scrollY / travel)) : 1;
      root.style.setProperty("--jp", String(progress));
      if (journey) journey.classList.toggle("arrived", progress > 0.92);
      ticking = false;
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });
  onScroll();
})();
