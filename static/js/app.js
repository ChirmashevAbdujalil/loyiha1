(function () {
  "use strict";

  function icons() {
    if (window.lucide) window.lucide.createIcons();
  }
  icons();

  // ---- Mobil menyu
  document.querySelectorAll("[data-toggle-nav]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      document.body.classList.toggle("nav-open");
    });
  });
  document.addEventListener("click", function (e) {
    if (document.body.classList.contains("nav-open") && !e.target.closest(".sidebar")) {
      document.body.classList.remove("nav-open");
    }
  });

  // ---- Dropdownlar
  document.querySelectorAll("[data-dropdown]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var dd = btn.closest(".dropdown");
      var wasOpen = dd.classList.contains("open");
      document.querySelectorAll(".dropdown.open").forEach(function (d) { d.classList.remove("open"); });
      if (!wasOpen) {
        dd.classList.add("open");
        if (dd.id === "notif-dropdown") loadFeed(true);
      }
    });
  });
  document.addEventListener("click", function (e) {
    if (!e.target.closest(".dropdown-menu")) {
      document.querySelectorAll(".dropdown.open").forEach(function (d) { d.classList.remove("open"); });
    }
  });

  // ---- Ctrl+K qidiruv
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      var s = document.getElementById("global-search");
      if (s) { e.preventDefault(); s.focus(); }
    }
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop.open").forEach(function (m) { m.classList.remove("open"); });
    }
  });

  // ---- Modallar
  document.querySelectorAll("[data-modal-open]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var m = document.getElementById(btn.getAttribute("data-modal-open"));
      if (m) {
        m.classList.add("open");
        var first = m.querySelector("textarea, input:not([type=hidden])");
        if (first) setTimeout(function () { first.focus(); }, 50);
      }
    });
  });
  document.querySelectorAll("[data-modal-close]").forEach(function (btn) {
    btn.addEventListener("click", function () { btn.closest(".modal-backdrop").classList.remove("open"); });
  });
  document.querySelectorAll(".modal-backdrop").forEach(function (m) {
    m.addEventListener("click", function (e) { if (e.target === m) m.classList.remove("open"); });
  });

  // ---- O'chirishni tasdiqlash
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  // ---- Fayl yuklash (drag & drop + ro'yxat)
  function humanSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }
  document.querySelectorAll(".dropzone").forEach(function (zone) {
    var input = zone.querySelector("input[type=file]");
    var list = document.getElementById(zone.getAttribute("data-list"));
    var dt = new DataTransfer();
    function render() {
      if (!list) return;
      list.innerHTML = "";
      Array.prototype.forEach.call(dt.files, function (f, i) {
        var row = document.createElement("div");
        row.className = "file-item";
        row.innerHTML = '<span class="fi"><i data-lucide="file"></i></span><div class="grow"><div class="nm"></div>' +
          '<div class="sz">' + humanSize(f.size) + '</div></div>' +
          '<button type="button" class="btn btn-sm btn-ghost btn-icon" title="Olib tashlash"><i data-lucide="x"></i></button>';
        row.querySelector(".nm").textContent = f.name;
        row.querySelector("button").addEventListener("click", function () {
          var next = new DataTransfer();
          Array.prototype.forEach.call(dt.files, function (g, j) { if (j !== i) next.items.add(g); });
          dt = next; input.files = dt.files; render();
        });
        list.appendChild(row);
      });
      icons();
    }
    function add(files) {
      Array.prototype.forEach.call(files, function (f) { dt.items.add(f); });
      input.files = dt.files;
      render();
    }
    input.addEventListener("change", function () {
      var picked = Array.prototype.slice.call(input.files);
      input.files = dt.files;
      add(picked);
    });
    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("drag"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("drag"); });
    });
    zone.addEventListener("drop", function (e) { add(e.dataTransfer.files); });
  });

  // ---- Bildirishnomalar (har 30 soniyada yangilanadi)
  var feedUrl = window.NOTIF_FEED_URL;
  var lastSeenId = null;
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }
  function toast(item) {
    var box = document.getElementById("toasts");
    if (!box) return;
    var t = document.createElement("a");
    t.className = "toast";
    t.href = item.url;
    t.innerHTML = '<span class="ic"><i data-lucide="bell-ring"></i></span><div class="grow"><b>' + esc(item.title) +
      '</b><div class="small muted">' + esc(item.message) + '</div></div>';
    box.appendChild(t);
    icons();
    setTimeout(function () { t.remove(); }, 8000);
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) {
      try { new Notification(item.title, { body: item.message }); } catch (e) { /* ignore */ }
    }
  }
  function loadFeed(renderList) {
    if (!feedUrl) return;
    fetch(feedUrl, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var dot = document.getElementById("notif-dot");
        if (dot) {
          dot.textContent = data.unread > 99 ? "99+" : data.unread;
          dot.classList.toggle("hidden", !data.unread);
        }
        document.querySelectorAll("[data-unread-count]").forEach(function (el) { el.textContent = data.unread; });
        var newest = data.items.length ? data.items[0].id : 0;
        if (lastSeenId !== null && newest > lastSeenId) {
          data.items.filter(function (i) { return i.id > lastSeenId; }).reverse().forEach(toast);
        }
        lastSeenId = Math.max(lastSeenId || 0, newest);
        var list = document.getElementById("notif-list");
        if (list && (renderList || list.dataset.loaded)) {
          list.dataset.loaded = "1";
          if (!data.items.length) {
            list.innerHTML = '<div class="empty"><i data-lucide="bell-off"></i><div>Yangi bildirishnoma yo\'q</div></div>';
          } else {
            list.innerHTML = data.items.map(function (i) {
              return '<a class="item" href="' + i.url + '"><span class="avatar sm"><i data-lucide="bell" style="width:13px;height:13px"></i></span>' +
                '<div class="grow"><div class="t">' + esc(i.title) + '</div><div class="small muted">' + esc(i.message) +
                '</div><div class="small text-muted">' + esc(i.time) + '</div></div></a>';
            }).join("");
          }
          icons();
        }
      })
      .catch(function () { /* tarmoq xatosi — keyingi safar */ });
  }
  if (feedUrl) {
    loadFeed(false);
    setInterval(function () { loadFeed(false); }, 30000);
    if ("Notification" in window && Notification.permission === "default") {
      document.addEventListener("click", function ask() {
        Notification.requestPermission();
        document.removeEventListener("click", ask);
      }, { once: true });
    }
  }

  window.App = { icons: icons };
})();
