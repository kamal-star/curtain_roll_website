/* Home page hero slider: fade between slides, arrows, dots, autoplay. */
(function () {
	"use strict";

	var INTERVAL_MS = 5500;

	function init() {
		var hero = document.querySelector(".cr-hero");
		if (!hero) return;

		var slides = [].slice.call(hero.querySelectorAll(".cr-slide"));
		var dots = [].slice.call(hero.querySelectorAll(".cr-dot"));
		if (slides.length < 2) return;

		var index = 0;
		var timer = null;

		function show(next) {
			index = (next + slides.length) % slides.length;
			slides.forEach(function (s, i) { s.classList.toggle("is-active", i === index); });
			dots.forEach(function (d, i) { d.classList.toggle("is-active", i === index); });
		}

		function start() {
			stop();
			timer = setInterval(function () { show(index + 1); }, INTERVAL_MS);
		}
		function stop() {
			if (timer) { clearInterval(timer); timer = null; }
		}

		var prev = hero.querySelector(".cr-prev");
		var next = hero.querySelector(".cr-next");
		if (prev) prev.addEventListener("click", function () { show(index - 1); start(); });
		if (next) next.addEventListener("click", function () { show(index + 1); start(); });
		dots.forEach(function (d, i) {
			d.addEventListener("click", function () { show(i); start(); });
		});

		hero.addEventListener("mouseenter", stop);
		hero.addEventListener("mouseleave", start);
		document.addEventListener("visibilitychange", function () {
			if (document.hidden) stop(); else start();
		});

		// respect reduced-motion: show the first slide, no autoplay
		var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
		if (!reduce) start();
	}

	if (document.readyState !== "loading") init();
	else document.addEventListener("DOMContentLoaded", init);
})();
