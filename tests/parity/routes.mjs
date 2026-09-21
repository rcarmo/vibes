/** Exact native API routing. Adapters supply explicit routes, not broad substring fallbacks. */
export function createRequestDispatcher(definitions) {
  const routes = new Map();
  for (const definition of definitions) {
    const key = `${definition.method.toUpperCase()} ${definition.path}`;
    if (routes.has(key)) throw new Error(`Duplicate fixture route: ${key}`);
    if (!definition.path.startsWith('/') || typeof definition.respond !== 'function') throw new Error(`Invalid fixture route: ${key}`);
    routes.set(key, definition);
  }
  const requests = [], failures = [];
  return {
    requests, failures,
    async dispatch(request) {
      const url = new URL(request.url());
      const method = request.method().toUpperCase();
      const entry = {method, path:url.pathname, query:url.search};
      requests.push(entry);
      const definition = routes.get(`${method} ${url.pathname}`);
      try {
        if (!definition) throw new Error(`Unknown fixture request: ${method} ${url.pathname}`);
        if (definition.validate) await definition.validate({request,url});
        else if (url.search) throw new Error(`Undeclared query scope: ${method} ${url.pathname}${url.search}`);
        return await definition.respond({request,url});
      } catch (error) {
        failures.push({...entry,error:error.message});
        throw error;
      }
    },
    assertRequests() {
      if (failures.length) throw new Error(`Fixture request failures: ${JSON.stringify(failures)}`);
    },
  };
}
