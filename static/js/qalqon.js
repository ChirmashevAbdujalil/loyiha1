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

  // ---- Joylashuvni aniqlab forma yuborish: <form data-geo data-lat data-lng data-radius data-map="id">
  document.querySelectorAll("form[data-geo]").forEach(function (form) {
    var status = form.querySelector(".geo-status");
    var btn = form.querySelector("[data-geo-submit]");
    var targetLat = parseFloat(form.dataset.lat), targetLng = parseFloat(form.dataset.lng);
    var radius = parseFloat(form.dataset.radius);
    var maxAcc = parseFloat(form.dataset.maxAccuracy || "150");
    var ready = false;
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
      btn.disabled = true;
      var original = btn.innerHTML;
      btn.innerHTML = '<span class="pulse"></span> Joylashuv aniqlanmoqda…';
      say('<span class="pulse"></span> GPS orqali joylashuvingiz aniqlanmoqda, kuting…');
      navigator.geolocation.getCurrentPosition(function (pos) {
        var la = pos.coords.latitude, ln = pos.coords.longitude, acc = pos.coords.accuracy;
        form.querySelector("[name=latitude]").value = la.toFixed(6);
        form.querySelector("[name=longitude]").value = ln.toFixed(6);
        form.querySelector("[name=accuracy]").value = Math.round(acc);
        if (form.dataset.map) showUser(form.dataset.map, la, ln, acc);
        var dist = haversine(la, ln, targetLat, targetLng);
        if (acc > maxAcc) {
          say("GPS aniqligi past: ±" + Math.round(acc) + " m (kerak: ±" + maxAcc + " m). Ochiq joyga chiqib qayta urining.", "err");
          btn.disabled = false; btn.innerHTML = original; return;
        }
        if (dist > radius) {
          say("Siz naryad hududidan tashqaridasiz: binogacha <b>" + Math.round(dist) + " m</b>, ruxsat etilgan radius <b>" +
            radius + " m</b>. Binoga yaqinlashib qayta urining.", "err");
          btn.disabled = false; btn.innerHTML = original; return;
        }
        say("Joylashuv mos keldi (" + Math.round(dist) + " m). Yuborilmoqda…", "ok");
        ready = true;
        form.submit();
      }, function (err) {
        say(GEO_ERRORS[err.code] || "Joylashuvni aniqlashda xatolik.", "err");
        btn.disabled = false; btn.innerHTML = original;
      }, { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 });
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
      navigator.geolocation.getCurrentPosition(function (pos) {
        latIn.value = pos.coords.latitude.toFixed(6);
        lngIn.value = pos.coords.longitude.toFixed(6);
        var m = maps[btn.dataset.map];
        if (m && m.sync) m.sync();
        btn.disabled = false; btn.innerHTML = original;
        if (window.App) window.App.icons();
      }, function (err) {
        alert(GEO_ERRORS[err.code] || "Joylashuvni aniqlab bo'lmadi.");
        btn.disabled = false; btn.innerHTML = original;
      }, { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 });
    });
  });

  window.Qalqon = { maps: maps, haversine: haversine };
})();
