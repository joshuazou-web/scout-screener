async function call(method, path, body) {
  const res = await fetch('/api' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败（${res.status}）`);
  return data;
}

export const api = {
  criteria: () => call('GET', '/criteria'),
  list: () => call('GET', '/projects'),
  create: (p = {}) => call('POST', '/projects', p),
  update: (p) => call('PUT', `/projects/${p.id}`, p),
  remove: (id) => call('DELETE', `/projects/${id}`),
  extract: (id, transcript) => call('POST', `/projects/${id}/extract`, { transcript }),
  report: () => call('GET', '/report'),
  exportAll: () => call('GET', '/export'),
  importAll: (items) => call('POST', '/import', items),
  resetSample: () => call('POST', '/reset-sample'),
};
