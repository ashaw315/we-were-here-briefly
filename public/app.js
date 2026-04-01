/**
 * WE WERE HERE, BRIEFLY — fullscreen datamosh video.
 *
 * Fetches the latest run from /api/runs?latest to get the
 * datamosh_url (R2). Falls back to local datamosh.mp4 for
 * development (python -m http.server from project root).
 */

(function () {
  "use strict";

  var video = document.getElementById("video");

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
      if (run.datamosh_url) {
        play(run.datamosh_url);
      } else {
        play("../output/datamosh.mp4");
      }
    })
    .catch(function () {
      play("../output/datamosh.mp4");
    });

})();
