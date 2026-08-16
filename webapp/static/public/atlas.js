/* The Living Atlas — poster page behaviour.
 *
 * Plays one sanitized replay from replay.json over the three.js atlas relief
 * board (board3d.js), built from ATLAS_BOARD (board.js). Fetches nothing else.
 * Never contacts the live server.
 *
 * Visual contract (docs/MARKETING_CLOSED_ALPHA.md): twelve cities at their
 * exact x/y under one uniform scale, the roads exactly as listed, a terrain
 * mound around each city — local relief only — and empty space left empty. The
 * page may tilt and rotate the board; it may not add geography. Every height in
 * the scene comes from a city's own terrain label. See board3d.js.
 *
 * The match this file was built against is decided by movement, not battle:
 * two forces grow from one piece to fifteen and march back and forth along the
 * Dreliwick-Narunon road while a lone commander walks west. So pieces travel
 * their road between turns rather than jumping, and the road they take lights
 * up as they use it. That motion is the whole show.
 */
import { createBoard } from "./board3d.js?v=h3";

(function () {
  "use strict";

  var TURN_MS = 1150; // time a turn is held
  var MOVE_MS = 720;  // time a piece takes to travel
  var STAGGER_MS = 22;// per-piece delay, so a column moves as a column
  var END_HOLD_MS = 3000;
  var GROW_MS = 380;  // a recruit growing in where it was raised

  // mapview.FACTION_COLORS[0] and [1]: the same vermilion and steel blue the
  // game gives seat one and seat two, so a reader coming from the game sees
  // the same two sides.
  var SEAT_COLORS = ["#d4553f", "#4a90d9"];

  var reducedMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------- utils */

  function byId(id) { return document.getElementById(id); }

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function pieceOrder(id) {
    var n = /(\d+)$/.exec(id);
    return n ? Number(n[1]) : 0;
  }

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  /* ------------------------------------------------------------ the board */

  var board = null;                 // the three.js relief board
  var cityById = {};

  ATLAS_BOARD.cities.forEach(function (city) { cityById[city.id] = city; });

  function buildBoard(activeCities) {
    board = createBoard({
      canvas: byId("atlas"),
      labelHost: byId("atlas-labels"),
      cities: ATLAS_BOARD.cities,
      roads: ATLAS_BOARD.roads,
      seatColors: SEAT_COLORS,
      activeCities: activeCities,
      reducedMotion: reducedMotion
    });
    board.setFrameCallback(tick);
    board.renderOnIdleChange();
    // A reduced-motion board is a still life: draw it once and then only when
    // the reader turns it, rather than burning a GPU on an unchanging scene.
    if (!reducedMotion) { board.startLoop(); } else { board.renderOnce(); }
  }

  /* ----------------------------------------------------------- the replay */

  var replay = null;
  var seatIndex = {};
  var seatLabel = {};
  var frameIndex = 0;
  var playing = false;
  var turnTimer = null;
  var tokens = {};      // piece id -> token record
  var animating = false;
  var animStart = 0;

  function seatColor(seatId) { return SEAT_COLORS[seatIndex[seatId] || 0]; }

  /* Where piece k of a seat stands at a city, in board world units.
     Deterministic, so a piece keeps its place in the column between turns and
     only moves when it really moves. */
  function slot(city, seatIdx, seatCount, k, total) {
    return board.slot(city, seatIdx, seatCount, k, total);
  }

  function layoutFrame(frame) {
    var byCity = {};
    frame.pieces.forEach(function (piece) {
      var bucket = byCity[piece.city_id] || (byCity[piece.city_id] = {});
      (bucket[piece.seat] || (bucket[piece.seat] = [])).push(piece);
    });

    var places = {};
    Object.keys(byCity).forEach(function (cityId) {
      var city = cityById[cityId];
      if (!city) { return; }
      var seats = Object.keys(byCity[cityId]).sort(function (a, b) {
        return (seatIndex[a] || 0) - (seatIndex[b] || 0);
      });
      seats.forEach(function (seatId, seatIdx) {
        var list = byCity[cityId][seatId].slice().sort(function (a, b) {
          if (a.kind !== b.kind) { return a.kind === "character" ? -1 : 1; }
          return pieceOrder(a.id) - pieceOrder(b.id);
        });
        list.forEach(function (piece, k) {
          places[piece.id] = slot(city, seatIdx, seats.length, k, list.length);
          places[piece.id].cityId = cityId;
        });
      });
    });
    return places;
  }

  function applyFrame(index, animate) {
    var frame = replay.frames[index];
    if (!frame) { return; }

    var places = layoutFrame(frame);
    var now = performance.now();
    var seen = {};
    var moveCount = 0;
    var live = animate && !reducedMotion;

    frame.pieces.forEach(function (piece) {
      var place = places[piece.id];
      if (!place) { return; }
      seen[piece.id] = true;

      var token = tokens[piece.id];
      var fresh = false;
      if (!token) {
        fresh = true;
        token = tokens[piece.id] = {
          node: board.addToken(piece.kind, seatIndex[piece.seat] || 0,
                               place.x, place.z),
          x: place.x, z: place.z,
          cityId: place.cityId,
          seat: piece.seat,
          presence: 0, presenceFrom: 0, presenceTo: 1, presenceAt: now,
          leaving: false
        };
      }

      var moved = token.cityId !== place.cityId;
      if (moved) {
        board.pulseRoad(token.cityId, place.cityId, seatColor(piece.seat));
        token.cityId = place.cityId;
      }

      token.fromX = token.x;
      token.fromZ = token.z;
      token.toX = place.x;
      token.toZ = place.z;
      token.moved = moved;
      token.delay = moved ? (moveCount++ % 8) * STAGGER_MS : 0;

      if (fresh && live) {
        // A recruit grows in where it was raised.
        token.presenceFrom = 0;
        token.presenceTo = 1;
        token.presenceAt = now;
      } else {
        token.presence = 1;
        token.presenceFrom = 1;
        token.presenceTo = 1;
        board.setTokenPresence(token.node, 1);
      }
    });

    // Pieces that left the board shrink away where they stood.
    Object.keys(tokens).forEach(function (id) {
      var token = tokens[id];
      if (seen[id] || token.leaving) { return; }
      if (!live) {
        board.dropToken(token.node);
        delete tokens[id];
        return;
      }
      token.leaving = true;
      token.presenceFrom = token.presence;
      token.presenceTo = 0;
      token.presenceAt = now;
      token.fromX = token.toX = token.x;
      token.fromZ = token.toZ = token.z;
      token.delay = 0;
      token.moved = false;
    });

    animStart = now;
    if (!live) {
      Object.keys(tokens).forEach(function (id) {
        var token = tokens[id];
        token.x = token.toX; token.z = token.toZ;
        board.moveToken(token.node, token.x, token.z, 0);
      });
    }

    paintCities(frame);
    paintReadouts(frame);
    paintTurn(index, frame);
  }

  /* Runs every rendered frame, driven by the board's own loop. */
  function tick(now) {
    Object.keys(tokens).forEach(function (id) {
      var token = tokens[id];

      if (token.toX !== undefined) {
        var t = (now - animStart - (token.delay || 0)) / MOVE_MS;
        if (t < 0) { t = 0; } else if (t > 1) { t = 1; }
        var e = easeInOutCubic(t);
        token.x = token.fromX + (token.toX - token.fromX) * e;
        token.z = token.fromZ + (token.toZ - token.fromZ) * e;
        // A marching piece lifts a little off the board mid-stride.
        var lift = token.moved ? Math.sin(Math.PI * t) * 2.4 : 0;
        board.moveToken(token.node, token.x, token.z, lift);
      }

      if (token.presence !== token.presenceTo) {
        var p = (now - token.presenceAt) / GROW_MS;
        if (p < 0) { p = 0; } else if (p > 1) { p = 1; }
        token.presence = token.presenceFrom +
          (token.presenceTo - token.presenceFrom) * easeInOutCubic(p);
        board.setTokenPresence(token.node, token.presence);
        if (p >= 1 && token.presenceTo === 0) {
          board.dropToken(token.node);
          delete tokens[id];
        }
      }
    });
  }

  function paintCities(frame) {
    frame.cities.forEach(function (city) {
      var occupied = city.occupied_by || [];
      board.paintCity(
        city.id,
        city.secured_by ? seatColor(city.secured_by) : null,
        occupied.length ? seatColor(occupied[0]) : null
      );
    });
  }

  function paintReadouts(frame) {
    replay.seats.forEach(function (seat) {
      var forces = frame.pieces.filter(function (p) {
        return p.seat === seat.id;
      }).length;
      var held = frame.cities.filter(function (c) {
        return c.secured_by === seat.id;
      }).length;
      var standing = frame.cities.filter(function (c) {
        return (c.occupied_by || []).indexOf(seat.id) !== -1;
      }).length;

      byId("stat-forces-" + seat.id).textContent = forces;
      byId("stat-held-" + seat.id).textContent = held;
      byId("stat-cities-" + seat.id).textContent = standing;
    });
  }

  function paintTurn(index, frame) {
    byId("turn-label").textContent = pad2(frame.turn);
    byId("scrub").value = String(index);

    var ticks = byId("ticks").children;
    for (var i = 0; i < ticks.length; i++) {
      ticks[i].className = "tick" +
        (i === index ? " is-now" : (i < index ? " is-past" : ""));
    }

    var outcome = byId("replay-outcome");
    if (index === replay.frames.length - 1 && replay.result) {
      outcome.textContent = "Turn " + frame.turn + ". " +
        (seatLabel[replay.result.winner_seat] || replay.result.winner_seat) +
        " ends ahead, decided by " + replay.result.decided_by + ".";
    } else {
      outcome.textContent = "";
    }
  }

  /* ---------------------------------------------------------- transport */

  function step() {
    var last = replay.frames.length - 1;
    var wasLast = frameIndex >= last;
    frameIndex = wasLast ? 0 : frameIndex + 1;
    applyFrame(frameIndex, !wasLast);
    schedule(frameIndex === last ? END_HOLD_MS : TURN_MS);
  }

  function schedule(ms) {
    window.clearTimeout(turnTimer);
    if (playing) { turnTimer = window.setTimeout(step, ms); }
  }

  function setPlaying(on) {
    playing = on;
    var button = byId("play");
    button.classList.toggle("is-playing", on);
    button.setAttribute("aria-label", on ? "Pause replay" : "Play replay");
    byId("play-word").textContent = on ? "Pause" : "Play";
    if (on) { schedule(TURN_MS); } else { window.clearTimeout(turnTimer); }
  }

  /* ------------------------------------------------------------- chrome */

  function buildReadouts() {
    var host = byId("readouts");
    replay.seats.forEach(function (seat, i) {
      var card = document.createElement("div");
      card.className = "readout";
      card.style.setProperty("--seat", SEAT_COLORS[i]);
      card.innerHTML =
        '<span class="readout-name"></span>' +
        '<div class="readout-stats">' +
          '<span>forces<b id="stat-forces-' + seat.id + '">0</b></span>' +
          '<span>standing<b id="stat-cities-' + seat.id + '">0</b></span>' +
          '<span>secured<b id="stat-held-' + seat.id + '">0</b></span>' +
        '</div>';
      card.querySelector(".readout-name").textContent = seat.label;
      host.appendChild(card);
    });
  }

  function buildTicks(movesPerTurn) {
    var host = byId("ticks");
    var peak = Math.max.apply(null, movesPerTurn.concat([1]));
    movesPerTurn.forEach(function (moves) {
      var tick = document.createElement("span");
      tick.className = "tick";
      tick.style.height = (2 + Math.round((moves / peak) * 14)) + "px";
      host.appendChild(tick);
    });
  }

  function buildLegend() {
    var host = byId("legend");
    replay.seats.forEach(function (seat, i) {
      var item = document.createElement("li");
      var swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = SEAT_COLORS[i];
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(seat.label));
      host.appendChild(item);
    });
    [
      ["swatch is-ring", "secured"],
      ["swatch is-ring is-dashed", "standing"]
    ].forEach(function (pair) {
      var item = document.createElement("li");
      var swatch = document.createElement("span");
      swatch.className = pair[0];
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(pair[1]));
      host.appendChild(item);
    });
    var note = document.createElement("li");
    note.textContent = "large token = commander";
    host.appendChild(note);
  }

  function start(data) {
    replay = data;
    replay.seats.forEach(function (seat, i) {
      seatIndex[seat.id] = i;
      seatLabel[seat.id] = seat.label;
    });

    var activeCities = {};
    var movesPerTurn = [];
    var previous = null;
    replay.frames.forEach(function (frame) {
      var here = {};
      var moves = 0;
      frame.pieces.forEach(function (piece) {
        activeCities[piece.city_id] = true;
        here[piece.id] = piece.city_id;
        if (previous && previous[piece.id] && previous[piece.id] !== piece.city_id) {
          moves += 1;
        }
      });
      movesPerTurn.push(moves);
      previous = here;
    });

    buildBoard(activeCities);
    buildReadouts();
    buildTicks(movesPerTurn);
    buildLegend();

    var label = replay.label === "official-gate"
      ? "Official gate replay" : "Exhibition replay";
    byId("replay-meta").textContent =
      label + " · " + replay.match_id + " · " + replay.turns + " turns";

    var scrub = byId("scrub");
    scrub.max = String(replay.frames.length - 1);
    scrub.addEventListener("input", function () {
      setPlaying(false);
      frameIndex = Number(scrub.value);
      applyFrame(frameIndex, false);
    });
    byId("play").addEventListener("click", function () { setPlaying(!playing); });

    applyFrame(0, false);

    // Do not animate an unseen board: start when it is actually on screen.
    if (reducedMotion) { setPlaying(false); return; }
    if (!("IntersectionObserver" in window)) { setPlaying(true); return; }
    var started = false;
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        // The render loop follows visibility too. A 3D scene left spinning
        // three screens above the fold costs a phone its battery for nothing.
        if (entry.isIntersecting) {
          board.startLoop();
          if (!started) { started = true; setPlaying(true); }
        } else {
          board.stopLoop();
          if (started && playing) { setPlaying(false); }
        }
      });
    }, { threshold: 0.25 });
    observer.observe(byId("atlas"));
  }

  function loadReplay() {
    fetch("replay.json", { cache: "no-cache" })
      .then(function (response) {
        if (!response.ok) { throw new Error("replay.json " + response.status); }
        return response.json();
      })
      .then(function (data) {
        if (data.map !== ATLAS_BOARD.map) {
          throw new Error("replay is for " + data.map +
            ", board is " + ATLAS_BOARD.map);
        }
        if (!data.frames || !data.frames.length) {
          throw new Error("replay has no frames");
        }
        start(data);
      })
      .catch(function (err) {
        var status = byId("board-status");
        status.textContent = "The replay could not be loaded.";
        status.hidden = false;
        byId("play").disabled = true;
        byId("scrub").disabled = true;
        if (window.console) { console.error(err); }
      });
  }

  /* ------------------------------------------------------------- the form */

  var ALLOWED_SRC = { hn: true, x: true, reddit: true };
  var MIN_DOCTRINE = 12;

  function captureSource() {
    var value = new URLSearchParams(window.location.search).get("src");
    byId("src").value = ALLOWED_SRC[value] ? value : "other";
  }

  function looksLikeHandle(value) {
    var v = value.trim();
    if (v.length < 2 || v.length > 80) { return false; }
    if (/\s/.test(v)) { return false; }
    if (/^https?:/i.test(v) || v.indexOf("/") !== -1) { return false; }
    if (/@[\w.-]+\.[a-z]{2,}$/i.test(v)) { return false; }  // an email address
    return /^@?[\w.#-]{2,}$/.test(v);
  }

  // Deliberately loose. The only job is to catch a typo before it costs us a
  // delivery channel; anything stricter rejects addresses that are perfectly
  // real. The vendor and the operator both see it again before a code is sent.
  function looksLikeEmail(value) {
    var v = value.trim();
    if (v.length < 6 || v.length > 120) { return false; }
    if (/\s/.test(v)) { return false; }
    return /^[^@]+@[^@.]+(\.[^@.]+)+$/.test(v);
  }

  function publishGate() {
    var form = byId("apply-form");
    var contact = byId("operator-contact");
    var missing = [];

    if (!form.dataset.endpoint) { missing.push("form vendor gate (data-endpoint)"); }
    if (!contact.dataset.contact) { missing.push("operator contact (data-contact)"); }

    contact.textContent = contact.dataset.contact || "—";
    if (!missing.length) { return true; }

    byId("publish-gate-reason").textContent =
      "Unresolved before this page may go live: " + missing.join("; ") + ".";
    byId("publish-gate").hidden = false;

    var submit = byId("submit");
    submit.disabled = true;
    submit.textContent = "Applications open shortly";
    return false;
  }

  function wireForm(live) {
    var form = byId("apply-form");
    var doctrine = byId("doctrine");
    var count = byId("doctrine-count");
    var error = byId("form-error");

    doctrine.addEventListener("input", function () {
      count.textContent = String(doctrine.value.trim().length);
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!live) { return; }
      error.hidden = true;

      // Honeypot: a filled value is a bot. Accept silently, submit nothing.
      if (byId("company").value) { form.reset(); return; }

      var name = byId("name").value.trim();
      var contact = byId("contact").value.trim();
      var email = byId("email").value.trim();
      var text = doctrine.value.trim();

      var problem = null;
      if (!name) {
        problem = "Please add a name.";
      } else if (!looksLikeHandle(contact)) {
        problem = "Please give an X or Discord handle. Other contact methods " +
          "are not accepted.";
      } else if (email && !looksLikeEmail(email)) {
        // Optional, but a typo here is worse than a blank: it is the channel
        // the invite code travels down. The form carries novalidate, so the
        // type="email" attribute checks nothing on its own.
        problem = "That email does not look right. Leave it blank if you " +
          "would rather be reached on your handle.";
      } else if (text.length < MIN_DOCTRINE) {
        problem = "One sentence of doctrine, at least " + MIN_DOCTRINE +
          " characters. One word is not enough.";
      } else if (recentlySubmitted(contact)) {
        problem = "You already applied today. One application per handle per " +
          "day; a later one replaces the earlier.";
      }

      if (problem) {
        error.textContent = problem;
        error.hidden = false;
        return;
      }

      var submit = byId("submit");
      submit.disabled = true;
      submit.textContent = "Sending…";

      fetch(form.dataset.endpoint, { method: "POST", body: new FormData(form) })
        .then(function (response) {
          if (!response.ok) { throw new Error("submit " + response.status); }
          markSubmitted(contact);
          var thanks = document.createElement("p");
          thanks.className = "thanks";
          thanks.textContent = "Thank you. Your application is in the queue. " +
            "You will hear back within 7 days, either way. Seats are issued " +
            "one at a time, and the operator answers every reply.";
          form.replaceChildren(thanks);
        })
        .catch(function () {
          submit.disabled = false;
          submit.textContent = "Apply for a seat";
          error.textContent = "That did not send. Please try again in a moment.";
          error.hidden = false;
        });
    });
  }

  // Courtesy throttle only. The binding one-per-day limit is the vendor's.
  function submitKey(contact) {
    return "tla-applied:" + contact.toLowerCase().replace(/^@/, "");
  }

  function recentlySubmitted(contact) {
    try {
      var at = window.localStorage.getItem(submitKey(contact));
      return Boolean(at) && (Date.now() - Number(at)) < 86400000;
    } catch (e) { return false; }
  }

  function markSubmitted(contact) {
    try {
      window.localStorage.setItem(submitKey(contact), String(Date.now()));
    } catch (e) { /* private mode; the vendor still enforces the limit */ }
  }

  /* ----------------------------------------------------------------- boot */

  loadReplay();
  captureSource();
  wireForm(publishGate());
})();
