/* Qalqon: xarita va joylashuvni aniqlash */
(function () {
  "use strict";

  function haversine(lat1, lng1, lat2, lng2) {
    var R = 6371000, toRad = Math.PI / 180;
    var dp = (lat2 - lat1) * toRad, dl = (lng2 - lng1) * toRad;
    var a = Math.sin(dp / 2) * Math.sin(dp / 2) +
      Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dl / 2) * Math.sin(dl / 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  var GEO_ERRORS = {
    1: "Joylashuvga ruxsat berilmadi. Brauzer sozlamalarida ushbu saytga joylashuv (GPS) ruxsatini yoqing.",
    2: "Joylashuvni aniqlab bo'lmadi. GPS yoqilganini tekshiring va ochiq joyda qayta urining.",
    3: "Joylashuvni aniqlash vaqti tugadi. Qayta urining."
  };

  // ---- Xaritalar: <div class="map" data-lat data-lng data-radius [data-pick] [data-user-lat ...]>
  var maps = {};
  function initMap(el) {
    if (!window.L) return null;
    var lat = parseFloat(el.dataset.lat), lng = parseFloat(el.dataset.lng);
    var hasPoint = !isNaN(lat) && !isNaN(lng);
    var center = hasPoint ? [lat, lng] : [41.311081, 69.240562];
    var map = L.map(el, { scrollWheelZoom: false }).setView(center, hasPoint ? 17 : 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap"
    }).addTo(map);
    var marker = null, circle = null;
    function draw(la, ln, r) {
      if (marker) { marker.setLatLng([la, ln]); } else { marker = L.marker([la, ln]).addTo(map); }
      if (circle) { circle.setLatLng([la, ln]); circle.setRadius(r); }
      else { circle = L.circle([la, ln], { radius: r, color: "#5b4ee6", fillColor: "#5b4ee6", fillOpacity: .12, weight: 2 }).addTo(map); }
    }
    if (hasPoint) draw(lat, lng, parseFloat(el.dataset.radius) || 100);
    (el.dataset.points ? JSON.parse(el.dataset.points) : []).forEach(function (p) {
      L.circleMarker([p.lat, p.lng], { radius: 7, color: p.ok ? "#17a34a" : "#e5484d", fillOpacity: .8 })
        .addTo(map).bindTooltip(p.label);
    });
    var api = {
      map: map,
      draw: draw,
      fit: function () { if (circle) map.fitBounds(circle.getBounds(), { padding: [20, 20] }); },
      user: null
    };
    if (hasPoint) api.fit();
    // Forma bilan bog'langan xarita: bosilgan joy koordinataga yoziladi
    if (el.dataset.pick) {
      var latIn = document.getElementById(el.dataset.latInput);
      var lngIn = document.getElementById(el.dataset.lngInput);
      var radIn = document.getElementById(el.dataset.radiusInput);
      var sync = function () {
        var la = parseFloat(latIn.value), ln = parseFloat(lngIn.value);
        if (!isNaN(la) && !isNaN(ln)) { draw(la, ln, parseFloat(radIn.value) || 100); }
      };
      map.on("click", function (e) {
        latIn.value = e.latlng.lat.toFixed(6);
        lngIn.value = e.latlng.lng.toFixed(6);
        sync();
      });
      [latIn, lngIn, radIn].forEach(function (i) { i.addEventListener("input", function () { sync(); api.fit(); }); });
      api.sync = function () { sync(); api.fit(); };
    }
    setTimeout(function () { map.invalidateSize(); }, 200);
    return api;
  }
  document.querySelectorAll(".map[data-map]").forEach(function (el) { maps[el.id] = initMap(el); });

  function showUser(mapId, la, ln, acc) {
    var m = maps[mapId];
    if (!m) return;
    if (m.user) { m.user.setLatLng([la, ln]); m.userAcc.setLatLng([la, ln]).setRadius(acc || 0); }
    else {
      m.userAcc = L.circle([la, ln], { radius: acc || 0, color: "#3567e8", weight: 1, fillOpacity: .08 }).addTo(m.map);
      m.user = L.circleMarker([la, ln], { radius: 8, color: "#fff", weight: 3, fillColor: "#3567e8", fillOpacity: 1 })
        .addTo(m.map).bindTooltip("Siz shu yerdasiz");
    }
    m.map.fitBounds(L.latLngBounds([[la, ln]]).extend(m.user.getLatLng()).extend(
      [parseFloat(document.getElementById(mapId).dataset.lat), parseFloat(document.getElementById(mapId).dataset.lng)]
    ), { padding: [40, 40], maxZoom: 18 });
  }

  var ACCURACY_TIPS = "<ul style=\"margin:6px 0 0 18px;padding:0\">" +
    "<li>Binodan tashqariga yoki deraza oldiga chiqing, 10–20 soniya kuting.</li>" +
    "<li>Telefonda <b>Joylashuv</b> yoqilgan va <b>aniq joylashuv</b> rejimida bo'lsin (Android: «Google aniq joylashuv»; " +
    "iPhone: Sozlamalar → Maxfiylik → Joylashuv → Safari/Chrome → «Aniq joylashuv»).</li>" +
    "<li>Noutbuk emas, telefon ishlating — noutbuk joyni Wi-Fi orqali taxminan aniqlaydi.</li></ul>";

  // GPS bir necha soniyada aniqlashadi: 20 soniyagacha kuzatib, eng aniq natijani olamiz.
  // Aniqlik `good` metrga yetsa — darhol to'xtaydi.
  function bestPosition(maxAcc, onProgress, onDone, onError) {
    var best = null, started = Date.now(), finished = false, watchId = null, timer = null;
    var good = Math.min(30, maxAcc);
    function finish() {
      if (finished) return;
      finished = true;
      if (watchId !== null) navigator.geolocation.clearWatch(watchId);
      clearInterval(timer);
      onDone(best);
    }
    watchId = navigator.geolocation.watchPosition(function (pos) {
      if (!best || pos.coords.accuracy < best.coords.accuracy) best = pos;
      if (best.coords.accuracy <= good) finish();
    }, function (err) {
      if (err.code === 1 || (!best && Date.now() - started > 20000)) {
        finished = true;
        if (watchId !== null) navigator.geolocation.clearWatch(watchId);
        clearInterval(timer);
        if (best && err.code !== 1) { onDone(best); } else { onError(err); }
      }
    }, { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 });
    timer = setInterval(function () {
      var secs = Math.round((Date.now() - started) / 1000);
      if (best && onProgress) onProgress(best.coords.accuracy, secs);
      if (secs >= 20 && best) finish();
      if (secs >= 30 && !best) { finished = true; navigator.geolocation.clearWatch(watchId); clearInterval(timer); onError({ code: 3 }); }
    }, 1000);
  }


  // ================================================================= jonli yuz tekshiruvi
  var FACE_CSS = ".face-modal{position:fixed;inset:0;background:rgba(10,14,24,.92);z-index:300;display:flex;align-items:center;" +
    "justify-content:center;padding:16px}.face-box{width:100%;max-width:420px;color:#fff;text-align:center}" +
    ".face-cam{position:relative;width:100%;aspect-ratio:3/4;border-radius:20px;overflow:hidden;background:#000;margin:12px 0}" +
    ".face-cam video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}" +
    ".face-oval{position:absolute;left:50%;top:46%;width:62%;height:62%;transform:translate(-50%,-50%);border:3px dashed rgba(255,255,255,.75);" +
    "border-radius:50%;box-shadow:0 0 0 999px rgba(0,0,0,.35)}.face-oval.go{border-color:#34d399;border-style:solid}" +
    ".face-step{font-size:20px;font-weight:800;min-height:56px}.face-sub{font-size:13px;opacity:.75;min-height:36px}" +
    ".face-count{position:absolute;right:14px;top:10px;font-size:40px;font-weight:800;text-shadow:0 2px 8px #000}" +
    ".face-dots{display:flex;gap:6px;justify-content:center;margin:6px 0}.face-dots i{width:28px;height:6px;border-radius:3px;background:rgba(255,255,255,.25)}" +
    ".face-dots i.on{background:#34d399}.face-btns{display:flex;gap:10px;justify-content:center;margin-top:10px}" +
    ".face-msg{margin-top:8px;padding:10px 12px;border-radius:10px;font-size:14px;text-align:left}.face-msg.err{background:#7f1d1d}.face-msg.ok{background:#065f46}";

  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function runFace(form) {
    if (!document.getElementById("face-css")) { var st = el("style"); st.id = "face-css"; st.textContent = FACE_CSS; document.head.appendChild(st); }
    var csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;
    var action = form.dataset.faceAction;
    var modal = el("div", "face-modal"), box = el("div", "face-box");
    var title = el("div", "face-step", "Jonli yuz tekshiruvi");
    var sub = el("div", "face-sub", "Old kamera ochiladi. Yuzingizni oval ichiga joylang.");
    var cam = el("div", "face-cam"), video = el("video"), oval = el("div", "face-oval"), count = el("div", "face-count");
    video.setAttribute("playsinline", ""); video.muted = true; video.autoplay = true;
    cam.appendChild(video); cam.appendChild(oval); cam.appendChild(count);
    var dots = el("div", "face-dots"), msg = el("div", "face-msg"), btns = el("div", "face-btns");
    msg.style.display = "none";
    var cancel = el("button", "btn", "Bekor qilish"), retry = el("button", "btn btn-success", "Qayta urinish");
    cancel.type = retry.type = "button"; retry.style.display = "none";
    btns.appendChild(cancel); btns.appendChild(retry);
    [title, sub, cam, dots, msg, btns].forEach(function (x) { box.appendChild(x); });
    modal.appendChild(box); document.body.appendChild(modal);

    var stream = null, closed = false;
    function stop() { if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; } }
    function close() { closed = true; stop(); modal.remove(); }
    function showMsg(text, cls) { msg.style.display = ""; msg.className = "face-msg " + cls; msg.textContent = text; }

    function capture() {
      var w = video.videoWidth, h = video.videoHeight, scale = Math.min(1, 640 / Math.max(w, h));
      var c = document.createElement("canvas"); c.width = Math.round(w * scale); c.height = Math.round(h * scale);
      c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
      return new Promise(function (res) { c.toBlob(res, "image/jpeg", 0.88); });
    }

    function post(url, data) {
      return fetch(url, { method: "POST", body: data, credentials: "same-origin", headers: { "X-CSRFToken": csrf } })
        .then(function (r) { return r.json().catch(function () { return { ok: false, message: "Server javobi noto'g'ri (" + r.status + ")." }; }); });
    }

    function attempt() {
      retry.style.display = "none"; msg.style.display = "none"; oval.classList.remove("go");
      var fd = new FormData(); fd.append("action", action);
      var challenge;
      return post(form.dataset.faceChallenge, fd).then(function (ch) {
        if (!ch.ok) throw new Error(ch.message);
        challenge = ch;
        dots.innerHTML = ""; ch.steps.forEach(function () { dots.appendChild(el("i")); });
        if (stream) return null;
        return navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 960 } }, audio: false })
          .then(function (s) { stream = s; video.srcObject = s; return video.play(); }, function (err) {
            throw new Error(err && err.name === "NotAllowedError"
              ? "Kameraga ruxsat berilmadi. Brauzer sozlamalarida ushbu sayt uchun kamerani yoqing."
              : "Old kamerani ochib bo'lmadi. Telefon kamerasi ishlayotganini tekshiring.");
          });
      }).then(function () { return sleep(700); }).then(function () {
        var frames = [], chain = Promise.resolve();
        challenge.steps.forEach(function (step, i) {
          chain = chain.then(function () {
            if (closed) throw new Error("cancel");
            title.textContent = step.text;
            sub.textContent = step.key === "center" ? "Yuzingiz oval ichida, yorug' tomonda bo'lsin" : "Boshingizni buring va shu holatda turing";
            var n = step.key === "center" ? 2 : 3;
            function tick() {
              count.textContent = n;
              if (n === 0) { count.textContent = ""; return capture(); }
              n -= 1; return sleep(800).then(tick);
            }
            return tick().then(function (blob) { frames.push(blob); dots.children[i].className = "on"; });
          });
        });
        return chain.then(function () { return frames; });
      }).then(function (frames) {
        title.textContent = "Tekshirilmoqda…"; sub.textContent = "Bir necha soniya kuting";
        var fd2 = new FormData(); fd2.append("action", action); fd2.append("nonce", challenge.nonce);
        frames.forEach(function (b, i) { fd2.append("frame_" + i, b, "frame_" + i + ".jpg"); });
        return post(form.dataset.faceVerify, fd2);
      }).then(function (res) {
        if (!res.ok) throw new Error(res.message);
        return res;
      });
    }

    return new Promise(function (resolve, reject) {
      cancel.onclick = function () { close(); reject(new Error("cancel")); };
      function go() {
        attempt().then(function (res) {
          oval.classList.add("go"); title.textContent = "Yuz tasdiqlandi"; showMsg(res.message, "ok");
          setTimeout(function () { close(); resolve(); }, 900);
        }, function (err) {
          if (closed) return;
          title.textContent = "Tekshiruvdan o'tilmadi"; sub.textContent = "";
          showMsg(err.message || "Xatolik yuz berdi.", "err"); retry.style.display = "";
        });
      }
      retry.onclick = go;
      go();
    });
  }

  // ---- Joylashuvni aniqlab forma yuborish: <form data-geo data-lat data-lng data-radius data-map="id">
  document.querySelectorAll("form[data-geo]").forEach(function (form) {
    var status = form.querySelector(".geo-status");
    var btn = form.querySelector("[data-geo-submit]");
    var targetLat = parseFloat(form.dataset.lat), targetLng = parseFloat(form.dataset.lng);
    var radius = parseFloat(form.dataset.radius);
    var maxAcc = parseFloat(form.dataset.maxAccuracy || "150");
    var ready = false, faceOk = false;
    function say(text, cls) {
      if (!status) return;
      status.className = "geo-status show " + (cls || "");
      status.innerHTML = text;
    }
    form.addEventListener("submit", function (e) {
      if (ready) return;
      e.preventDefault();
      if (!form.reportValidity()) return;
      if (!("geolocation" in navigator)) { say("Bu qurilma joylashuvni aniqlay olmaydi.", "err"); return; }
      if (!window.isSecureContext) {
        say("Joylashuvni aniqlash uchun sayt HTTPS orqali ochilishi kerak.", "err"); return;
      }
      // 1-qadam: jonli yuz tekshiruvi (yoqilgan bo'lsa), 2-qadam: GPS
      if (form.dataset.faceChallenge && !faceOk) {
        runFace(form).then(function () {
          faceOk = true;
          say("Yuz tasdiqlandi. Endi joylashuv aniqlanadi…", "ok");
          if (form.requestSubmit) { form.requestSubmit(btn); } else { form.dispatchEvent(new Event("submit", { cancelable: true })); }
        }, function () { /* bekor qilindi */ });
        return;
      }
      btn.disabled = true;
      var original = btn.innerHTML;
      btn.innerHTML = '<span class="pulse"></span> Joylashuv aniqlanmoqda…';
      say('<span class="pulse"></span> GPS orqali joylashuvingiz aniqlanmoqda, kuting…');
      bestPosition(maxAcc, function (acc, secs) {
        say('<span class="pulse"></span> GPS aniqligi: <b>±' + Math.round(acc) + " m</b> — aniqlashtirilmoqda (" + secs +
          " s)… Telefonni ochiq osmon tomon tuting.");
      }, function (pos) {
        var la = pos.coords.latitude, ln = pos.coords.longitude, acc = pos.coords.accuracy;
        form.querySelector("[name=latitude]").value = la.toFixed(6);
        form.querySelector("[name=longitude]").value = ln.toFixed(6);
        form.querySelector("[name=accuracy]").value = Math.round(acc);
        if (form.dataset.map) showUser(form.dataset.map, la, ln, acc);
        var dist = haversine(la, ln, targetLat, targetLng);
        if (acc > maxAcc) {
          say("GPS aniqligi past: ±" + Math.round(acc) + " m (kerak: ±" + maxAcc + " m yoki yaxshiroq)." + ACCURACY_TIPS, "err");
          btn.disabled = false; btn.innerHTML = original; return;
        }
        if (dist > radius) {
          say("Siz naryad hududidan tashqaridasiz: binogacha <b>" + Math.round(dist) + " m</b>, ruxsat etilgan radius <b>" +
            radius + " m</b>. Binoga yaqinlashib qayta urining.", "err");
          btn.disabled = false; btn.innerHTML = original; return;
        }
        say("Joylashuv mos keldi (" + Math.round(dist) + " m, ±" + Math.round(acc) + " m). Yuborilmoqda…", "ok");
        ready = true;
        form.submit();
      }, function (err) {
        say(GEO_ERRORS[err.code] || "Joylashuvni aniqlashda xatolik.", "err");
        btn.disabled = false; btn.innerHTML = original;
      });
    });
  });

  // ---- Joriy joylashuvni formaga yozish (sardor bino koordinatasini kiritayotganda)
  document.querySelectorAll("[data-use-my-location]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var latIn = document.getElementById(btn.dataset.latInput);
      var lngIn = document.getElementById(btn.dataset.lngInput);
      var original = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = "Aniqlanmoqda…";
      bestPosition(30, function (acc, secs) { btn.innerHTML = "±" + Math.round(acc) + " m (" + secs + " s)…"; }, function (pos) {
        latIn.value = pos.coords.latitude.toFixed(6);
        lngIn.value = pos.coords.longitude.toFixed(6);
        var m = maps[btn.dataset.map];
        if (m && m.sync) m.sync();
        btn.disabled = false; btn.innerHTML = original;
        if (window.App) window.App.icons();
      }, function (err) {
        alert(GEO_ERRORS[err.code] || "Joylashuvni aniqlab bo'lmadi.");
        btn.disabled = false; btn.innerHTML = original;
      });
    });
  });

  // Shablon shu belgiga qarab eski (yuz tekshiruvisiz) JS fayl yuklanganini aniqlaydi
  window.Qalqon = { maps: maps, haversine: haversine, runFace: runFace, faceSupport: 1 };
})();
