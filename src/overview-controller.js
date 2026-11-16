// Session-only overview state. Display changes never become extra provider calls.
export function overviewScopeKey(scope) {
  if (!scope?.datasetId || !scope?.provider || !scope?.model) return "";
  return JSON.stringify([scope.datasetId, scope.provider, scope.model,
    ["from", "to", "category", "product", "weekday", "period"].map(key => scope.filters?.[key] || "")]);
}

export class OverviewController {
  constructor({request, onChange, delay = 450, maxEntries = 6, ttl = 15 * 60 * 1000}) {
    Object.assign(this, {request, onChange, delay, maxEntries, ttl});
    this.cache = new Map();
    this.key = "";
    this.state = {status: "idle"};
    this.generation = 0;
  }

  emit(state) {
    this.state = state;
    this.onChange(state);
  }

  select(scope) {
    const key = overviewScopeKey(scope);
    if (key === this.key) return;
    clearTimeout(this.timer);
    this.controller?.abort();
    this.generation++;
    this.key = key;
    this.scope = scope;
    if (!key) return this.emit({status: "idle"});
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.saved < this.ttl) {
      this.cache.delete(key);
      this.cache.set(key, cached);
      return this.emit(cached.state);
    }
    this.cache.delete(key);
    this.emit({status: "scheduled"});
    this.timer = setTimeout(() => this.start(), this.delay);
  }

  retry() {
    if (!this.key || ["loading", "scheduled"].includes(this.state.status)) return;
    this.cache.delete(this.key);
    return this.start();
  }

  async start() {
    clearTimeout(this.timer);
    if (!this.key) return;
    const key = this.key, generation = ++this.generation, controller = new AbortController();
    this.controller?.abort();
    this.controller = controller;
    this.emit({status: "loading"});
    try {
      const response = await this.request({...this.scope, task: "overview"}, controller.signal);
      if (generation !== this.generation || controller.signal.aborted) return;
      const state = response?.status === "answered"
        ? {status: "ready", response}
        : {status: "error", response, error: response?.answer || "The AI could not finish this overview. Try again later."};
      this.remember(key, state);
    } catch (error) {
      if (generation !== this.generation || controller.signal.aborted) return;
      this.remember(key, {status: "error", error: error.message || "The AI overview could not be completed."});
    }
  }

  remember(key, state) {
    this.cache.set(key, {state, saved: Date.now()});
    while (this.cache.size > this.maxEntries) this.cache.delete(this.cache.keys().next().value);
    this.emit(state);
  }
}
