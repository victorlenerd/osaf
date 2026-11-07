// Progressive enhancement for /b/<slug> pages of businesses that Google knows: fetch up to five
// live Google reviews in the browser and show them with Google's attribution. They are never
// part of the rendered HTML (Places terms), and the section is marked data-nosnippet.
(function () {
  var el = document.getElementById("google-reviews");
  if (!el || !window.fetch) return;
  var id = el.getAttribute("data-place-id");
  var api = el.getAttribute("data-api");
  if (!id || !api) return;
  function text(tag, value, cls) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    n.textContent = value;
    return n;
  }
  fetch(api + "/api/places/" + encodeURIComponent(id) + "/google", { headers: { accept: "application/json" } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (!data || !data.reviews || !data.reviews.length) return;
      el.appendChild(text("h2", "On Google"));
      var place = data.place || {};
      if (place.rating != null) {
        el.appendChild(text("p", place.rating.toFixed(1) + "/5 from " + place.user_rating_count + " Google ratings", "muted small"));
      }
      data.reviews.forEach(function (rv) {
        var box = document.createElement("div");
        box.className = "g-review";
        var who = (rv.author_name || "Google user") + (rv.rating != null ? " · " + rv.rating + "/5" : "") + (rv.relative_time ? " · " + rv.relative_time : "");
        box.appendChild(text("p", who, "small muted"));
        if (rv.text) box.appendChild(text("p", rv.text));
        el.appendChild(box);
      });
      var attr = document.createElement("p");
      attr.className = "small muted";
      var link = document.createElement("a");
      link.href = place.google_maps_uri || "https://maps.google.com/";
      link.rel = "nofollow noopener";
      link.textContent = data.attribution || "Reviews from Google";
      attr.appendChild(link);
      el.appendChild(attr);
      el.hidden = false;
    })
    .catch(function () {});
})();
