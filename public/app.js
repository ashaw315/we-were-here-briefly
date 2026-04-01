/**
 * WE WERE HERE, BRIEFLY — simple video player + text overlay.
 *
 * Fetches the latest run from /api/runs?latest (Vercel Postgres).
 * Falls back to ../output/log.json if the API is unavailable.
 * Video plays fullscreen from R2 (or local fallback).
 */

(function () {
  "use strict";

  var video      = document.getElementById("video");
  var dateEl     = document.getElementById("date");
  var sentenceEl = document.getElementById("sentence");

  /**
   * Set up the video player and text overlay from a run object.
   */
  function showRun(run) {
    // Video source: prefer datamosh, fall back to individual video
    var src = run.datamosh_url || run.video_url;
    if (src) {
      video.src = src;
    } else {
      // Legacy local fallback
      video.src = "/datamosh.mp4";
    }

    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.loop = true;
    video.play().catch(function (e) {
      console.warn("Autoplay blocked:", e);
    });

    dateEl.textContent = run.date || "";
    sentenceEl.textContent = run.sentence || "";
    dateEl.style.opacity = "1";
    sentenceEl.style.opacity = "1";
  }

  /**
   * Try the Vercel Postgres API first, fall back to local log.json.
   */
  fetch("/api/runs?latest")
    .then(function (resp) {
      if (!resp.ok) throw new Error("API returned " + resp.status);
      return resp.json();
    })
    .then(function (run) {
      showRun(run);
    })
    .catch(function () {
      // API unavailable — fall back to local log.json
      console.warn("API unavailable, falling back to log.json");
      fetch("/log.json")
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          var entries = data.filter(function (e) {
            return e.video_url || e.video;
          });
          if (entries.length === 0) return;

          var latest = entries[entries.length - 1];
          showRun({
            date: latest.date,
            sentence: latest.sentence,
            datamosh_url: null,
            video_url: latest.video_url || latest.video,
          });
        })
        .catch(function (e) {
          console.warn("Could not load log.json:", e);
        });
    });

})();
