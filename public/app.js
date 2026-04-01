/**
 * WE WERE HERE, BRIEFLY — fullscreen datamosh video.
 *
 * Fetches the latest run from /api/runs/latest to get the
 * datamosh_url (R2). Falls back to R2 direct URL.
 */

(function () {
  "use strict";

  var video = document.getElementById("video");
  var R2_DATAMOSH = "https://pub-dfd09c6a5bcd43dda4ed449bb2e01d95.r2.dev/datamosh.mp4";

  async function loadVideo() {
    try {
      var res = await fetch("/api/runs/latest");
      if (!res.ok) throw new Error("API failed");
      var run = await res.json();
      if (run.datamosh_url) {
        video.src = run.datamosh_url;
        return;
      }
    } catch (e) {
      console.log("API unavailable:", e.message);
    }

    // Fallback to direct R2 datamosh URL
    video.src = R2_DATAMOSH;
  }

  video.muted = true;
  video.playsInline = true;
  video.autoplay = true;
  video.loop = true;

  loadVideo().then(function () {
    video.play().catch(function () {});
  });

})();
