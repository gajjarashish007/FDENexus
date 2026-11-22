/** Detect /eks mount prefix when pod UI is served on the unified Cloud Portal port. */
(function (global) {
  function detectMount() {
    var path = global.location.pathname || "";
    var markers = ["/dashboard.html", "/login", "/login.html", "/terminal-gui.html"];
    for (var i = 0; i < markers.length; i++) {
      var m = markers[i];
      var idx = path.indexOf(m);
      if (idx > 0) return path.slice(0, idx);
    }
    return "";
  }

  global.POD_MOUNT = detectMount();

  global.podUrl = function podUrl(url) {
    if (!url || typeof url !== "string") return url;
    if (/^https?:\/\//i.test(url)) return url;
    if (!url.startsWith("/")) return url;
    var base = global.POD_MOUNT || "";
    if (!base) return url;
    if (url === base || url.startsWith(base + "/")) return url;
    return base + url;
  };

  var nativeFetch = global.fetch.bind(global);
  global.fetch = function patchedFetch(input, init) {
    if (typeof input === "string") {
      input = podUrl(input);
    } else if (input && input.url) {
      return nativeFetch(input, init);
    }
    return nativeFetch(input, init);
  };
})(window);
