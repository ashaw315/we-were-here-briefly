/**
 * WE WERE HERE, BRIEFLY — fullscreen datamosh video.
 *
 * Fetches the latest run from /api/runs?latest to get the
 * datamosh_url (R2). Falls back to R2 direct URL, then local
 * datamosh.mp4 for development.
 */

(function () {
  "use strict";

  var video = document.getElementById("video");
  var R2_DATAMOSH = "https://pub-dfd09c6a5bcd43dda4ed449bb2e01d95.r2.dev/datamosh.mp4";

  function play(src) {
    video.src = src;
    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.loop = true;
    video.play().catch(function () {});
  }

  fetch("/api/runs?latest")
    .then(function (resp) {
      if (!resp.ok) throw new Error(resp.status);
      return resp.json();
    })
    .then(function (run) {
      play(run.datamosh_url || R2_DATAMOSH);
    })
    .catch(function () {
      play(R2_DATAMOSH);
    });

  // Local dev fallback — if R2 fails, try local file
  video.addEventListener("error", function () {
    if (video.src.indexOf("r2.dev") !== -1) {
      play("../output/datamosh.mp4");
    }
  });

})();
