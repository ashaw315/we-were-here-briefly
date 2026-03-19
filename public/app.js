/**
 * WE WERE HERE, BRIEFLY — video cycler with text overlay.
 *
 * Loads entries from output/log.json, plays each 5-second video
 * fullscreen, overlays the surreal sentence, and cycles infinitely.
 * Much simpler than the old WebGL approach — the videos ARE the effect.
 */

(function () {
  "use strict";

  // --- DOM ---
  const video = document.getElementById("video");
  const dateEl = document.getElementById("date");
  const sentenceEl = document.getElementById("sentence");

  // --- State ---
  let entries = [];       // All log entries from log.json
  let currentIndex = 0;   // Which entry is currently playing
  let nextVideo = null;    // Preloaded <video> element for the next entry

  // --- Initialization ---

  async function init() {
    // Fetch the log
    try {
      // log.json lives one level up from public/ — Vercel serves
      // from public/, so ../output/ reaches the output directory.
      const resp = await fetch("../output/log.json");
      entries = await resp.json();
    } catch (e) {
      console.warn("Could not load log.json:", e);
      entries = [];
    }

    // Filter to only entries that have a video
    entries = entries.filter(function (entry) {
      return entry.video;
    });

    if (entries.length === 0) {
      // Nothing to show yet — display a waiting message
      sentenceEl.textContent = "waiting for traces...";
      sentenceEl.style.opacity = 1;
      return;
    }

    // Start playing the first video
    playEntry(0);

    // When the current video ends, advance to the next one.
    // The "ended" event fires when a video reaches its end.
    // Even though we have `loop` on the <video> tag, we remove
    // it programmatically so we can control cycling ourselves.
    video.loop = false;
    video.addEventListener("ended", onVideoEnded);
  }

  /**
   * Play a specific log entry.
   *
   * Sets the video source, updates the text overlay, and starts
   * preloading the next video in the background.
   */
  function playEntry(index) {
    currentIndex = index;
    var entry = entries[currentIndex];

    // Set the video source.
    // Video paths in log.json are relative to output/
    // (e.g., "videos/2026-03-18.mp4").
    // From public/, we reach output/ via ../output/.
    video.src = "../output/" + entry.video;
    video.play().catch(function (e) {
      // Autoplay may be blocked by browser policy — log it but don't crash.
      // Most browsers allow autoplay if the video is muted (which ours is).
      console.warn("Autoplay blocked:", e);
    });

    // Update the text overlay
    dateEl.textContent = entry.date || "";
    sentenceEl.textContent = entry.sentence || "";

    // Fade in the text once the video starts playing.
    // We listen for the "playing" event which fires when
    // playback actually begins (after buffering).
    video.addEventListener("playing", function onPlaying() {
      // removeEventListener with the named function prevents
      // stacking multiple listeners on repeated calls.
      video.removeEventListener("playing", onPlaying);

      // Small delay before showing text — let the video
      // establish itself first
      setTimeout(function () {
        dateEl.style.opacity = 1;
        sentenceEl.style.opacity = 1;
      }, 500);
    });

    // Preload the next video in the background
    preloadNext();
  }

  /**
   * Preload the next video so the transition is seamless.
   *
   * Creates a hidden <video> element and sets its src.
   * The browser will start downloading it in the background.
   * When it's time to play, we just swap the src — the data
   * is already cached.
   */
  function preloadNext() {
    var nextIndex = (currentIndex + 1) % entries.length;
    var nextEntry = entries[nextIndex];

    // Create a throwaway <video> element just for preloading.
    // Setting preload="auto" tells the browser to download
    // the entire file, not just metadata.
    nextVideo = document.createElement("video");
    nextVideo.preload = "auto";
    nextVideo.src = "../output/" + nextEntry.video;
    nextVideo.load();
  }

  /**
   * Handle the video ending — fade out text, then advance.
   */
  function onVideoEnded() {
    // Fade out the text overlay
    dateEl.style.opacity = 0;
    sentenceEl.style.opacity = 0;

    // Wait for the CSS transition to finish (1s), then play next.
    // setTimeout is the same as in JS — no Python equivalent needed here.
    setTimeout(function () {
      var nextIndex = (currentIndex + 1) % entries.length;
      playEntry(nextIndex);
    }, 1000);
  }

  // --- Go ---
  init();
})();
