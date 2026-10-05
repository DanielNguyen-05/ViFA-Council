(function () {
  "use strict";

  // Outpainting gallery: one painting visible at a time.
  var picker = document.querySelector("[data-picker]");
  if (picker) {
    var tabs = Array.prototype.slice.call(picker.querySelectorAll("button"));
    var show = function (key) {
      tabs.forEach(function (tab) {
        var on = tab.dataset.key === key;
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.tabIndex = on ? 0 : -1;
        var panel = document.getElementById("op-" + tab.dataset.key);
        if (panel) panel.hidden = !on;
      });
    };
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { show(tab.dataset.key); });
      tab.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        show(next.dataset.key);
        next.focus();
      });
    });
  }

  // Story carousel: arrows scroll the snap track, counter follows the scroll position.
  var track = document.querySelector("[data-track]");
  if (track) {
    var slides = Array.prototype.slice.call(track.children);
    var count = document.querySelector("[data-count]");
    var current = function () {
      var mid = track.scrollLeft + track.clientWidth / 2;
      var best = 0;
      var dist = Infinity;
      slides.forEach(function (s, i) {
        var d = Math.abs(s.offsetLeft - track.offsetLeft + s.offsetWidth / 2 - mid);
        if (d < dist) { dist = d; best = i; }
      });
      return best;
    };
    var go = function (i) {
      var s = slides[Math.max(0, Math.min(slides.length - 1, i))];
      track.scrollTo({ left: s.offsetLeft - track.offsetLeft - (track.clientWidth - s.offsetWidth) / 2, behavior: "smooth" });
    };
    var update = function () { if (count) count.textContent = (current() + 1) + " / " + slides.length; };
    var prev = document.querySelector("[data-prev]");
    var next = document.querySelector("[data-next]");
    if (prev) prev.addEventListener("click", function () { go(current() - 1); });
    if (next) next.addEventListener("click", function () { go(current() + 1); });
    track.addEventListener("scroll", function () { window.requestAnimationFrame(update); }, { passive: true });
    update();
  }

  // Lightbox for any figure wrapped in a .zoom button.
  var box = null;
  var lastFocus = null;
  var close = function () {
    if (!box) return;
    box.remove();
    box = null;
    document.removeEventListener("keydown", onKey);
    if (lastFocus) lastFocus.focus();
  };
  var onKey = function (e) { if (e.key === "Escape") close(); };
  document.addEventListener("click", function (e) {
    var trigger = e.target.closest ? e.target.closest(".zoom") : null;
    if (!trigger) return;
    var img = trigger.querySelector("img");
    if (!img) return;
    lastFocus = trigger;
    box = document.createElement("div");
    box.className = "lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", img.alt || "Enlarged figure");
    var big = document.createElement("img");
    big.src = img.currentSrc || img.src;
    big.alt = img.alt;
    var btn = document.createElement("button");
    btn.className = "close";
    btn.type = "button";
    btn.textContent = "Close";
    box.appendChild(big);
    box.appendChild(btn);
    box.addEventListener("click", close);
    document.body.appendChild(box);
    document.addEventListener("keydown", onKey);
    btn.focus();
  });

  // Copy BibTeX.
  var copy = document.querySelector("[data-copy]");
  if (copy) {
    copy.addEventListener("click", function () {
      var pre = document.getElementById("bibtex-entry");
      var done = function () {
        copy.textContent = "Copied";
        window.setTimeout(function () { copy.textContent = "Copy"; }, 1600);
      };
      var select = function () {
        var range = document.createRange();
        range.selectNodeContents(pre);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(pre.textContent).then(done, select);
      } else {
        select();
      }
    });
  }
})();
