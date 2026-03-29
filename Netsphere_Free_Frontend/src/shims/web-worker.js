// Minimal browser shim for libraries expecting the "web-worker" package.
// ELK imports this module and constructs it via `new WebWorker(url)`.
export default class WebWorker extends Worker {
  constructor(url, options) {
    super(url, options);
  }
}
