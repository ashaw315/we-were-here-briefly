/**
 * WE WERE HERE, BRIEFLY — fullscreen datamosh video.
 *
 * Fetches the latest run from /api/runs/latest to get the
 * datamosh_url (an HLS .m3u8 playlist on R2). Plays it via HLS.js,
 * or native HLS in Safari. Falls back to the R2 direct .m3u8 URL.
 */

(function () {
  "use strict";

  var video = document.getElementById("video");
  var R2_HLS = "https://pub-dfd09c6a5bcd43dda4ed449bb2e01d95.r2.dev/hls/datamosh.m3u8";

  // Loop manually: HLS.js streams a VOD playlist that doesn't loop on
  // its own, so seek back to the start when it ends.
  function loopOnEnd() {
    video.addEventListener("ended", function () {
      video.currentTime = 0;
      video.play().catch(function () {});
    });
  }

  function playVideo(url) {
    if (url.endsWith(".m3u8")) {
      if (window.Hls && Hls.isSupported()) {
        var hls = new Hls({
          // Pick the first level immediately so playback starts on the
          // first chunk.
          startLevel: -1,
          // Keep the buffer small for memory efficiency.
          maxBufferLength: 30,
          maxMaxBufferLength: 60,
        });
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, function () {
          video.play().catch(function () {});
        });
        loopOnEnd();
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        // Native HLS support (Safari).
        video.src = url;
        loopOnEnd();
        video.play().catch(function () {});
      }
    } else {
      // Fallback for a plain mp4 URL.
      video.src = url;
      video.loop = true;
      video.play().catch(function () {});
    }
  }

  async function loadVideo() {
    try {
      var res = await fetch("/api/runs/latest");
      if (!res.ok) throw new Error("API failed");
      var run = await res.json();
      if (run.datamosh_url) {
        playVideo(run.datamosh_url);
        return;
      }
    } catch (e) {
      console.log("API unavailable:", e.message);
    }

    // Fallback to the R2 HLS playlist directly.
    playVideo(R2_HLS);
  }

  video.muted = true;
  video.playsInline = true;
  video.autoplay = true;

  loadVideo();

})();
