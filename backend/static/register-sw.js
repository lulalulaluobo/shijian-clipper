if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js")
      .then((reg) => {
        console.log("ServiceWorker registered successfully with scope: ", reg.scope);
      })
      .catch((err) => {
        console.warn("ServiceWorker registration failed: ", err);
      });
  });
}
