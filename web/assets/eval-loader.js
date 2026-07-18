(function () {
  const config = window.FOUNDRY_EVAL;
  if (!config?.token) return;

  const script = document.createElement("script");
  script.src = `${config.apiBase}/collectors/web/foundry-eval.js`;
  script.dataset.apiBase = config.apiBase;
  script.dataset.projectRef = config.projectRef;
  script.dataset.token = config.token;
  script.defer = true;
  document.body.appendChild(script);
})();
