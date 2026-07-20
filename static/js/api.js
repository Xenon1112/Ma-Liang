// REST API 封装层
const api = {
  async _fetch(url, options = {}) {
    const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  },

  _get(url, params) {
    // 过滤掉 null/undefined 参数
    const clean = {};
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined) clean[k] = v;
      }
    }
    const qs = Object.keys(clean).length ? '?' + new URLSearchParams(clean).toString() : '';
    return this._fetch(url + qs);
  },
  _post(url, data) { return this._fetch(url, { method: 'POST', body: JSON.stringify(data) }); },
  _put(url, data) { return this._fetch(url, { method: 'PUT', body: JSON.stringify(data) }); },
  _delete(url) { return this._fetch(url, { method: 'DELETE' }); },

  project: {
    list: () => api._get('/api/projects'),
    get: (id) => api._get(`/api/projects/${id}`),
    create: (data) => api._post('/api/projects', data),
    update: (id, fields) => api._put(`/api/projects/${id}`, fields),
    delete: (id) => api._delete(`/api/projects/${id}`),
    getStats: (id) => api._get(`/api/projects/${id}/stats`),
  },

  volume: {
    list: (projectId) => api._get('/api/volumes', { projectId }),
    get: (id) => api._get(`/api/volumes/${id}`),
    create: (data) => api._post('/api/volumes', data),
    update: (id, fields) => api._put(`/api/volumes/${id}`, fields),
    updatePreface: (id, content) => api._put(`/api/volumes/${id}/preface`, { content }),
    getPrefaceVersions: (id) => api._get(`/api/volumes/${id}/preface-versions`),
    delete: (id) => api._delete(`/api/volumes/${id}`),
    reorder: (projectId, orderedIds) => api._post('/api/volumes/reorder', { projectId, orderedIds }),
  },

  chapter: {
    list: (volumeId) => api._get('/api/chapters', { volumeId }),
    get: (id) => api._get(`/api/chapters/${id}`),
    create: (data) => api._post('/api/chapters', data),
    update: (id, fields) => api._put(`/api/chapters/${id}`, fields),
    delete: (id) => api._delete(`/api/chapters/${id}`),
    reorder: (volumeId, orderedIds) => api._post('/api/chapters/reorder', { volumeId, orderedIds }),
  },

  draft: {
    getCurrent: (chapterId, volumeId) => api._get('/api/drafts/current', { chapterId, volumeId }),
    save: (data) => api._post('/api/drafts', data),
    list: (chapterId, volumeId) => api._get('/api/drafts/list', { chapterId, volumeId }),
    get: (draftId) => api._get(`/api/drafts/${draftId}`),
    diff: (draftIdA, draftIdB) => api._post('/api/drafts/diff', { draftIdA, draftIdB }),
    rollback: (draftId) => api._post(`/api/drafts/${draftId}/rollback`),
    delete: (draftId) => api._delete(`/api/drafts/${draftId}`),
    createSnapshot: (data) => api._post('/api/drafts/snapshot', data),
    cleanOldVersions: (params) => api._post('/api/drafts/clean', params),
  },

  outline: {
    tree: (projectId) => api._get('/api/outlines', { projectId }),
    get: (id) => api._get(`/api/outlines/${id}`),
    create: (data) => api._post('/api/outlines', data),
    update: (id, fields) => api._put(`/api/outlines/${id}`, fields),
    delete: (id) => api._delete(`/api/outlines/${id}`),
    reorder: (projectId, orderedIds) => api._post('/api/outlines/reorder', { projectId, orderedIds }),
    linkChapter: (id, chapterId) => api._post(`/api/outlines/${id}/link`, { chapterId }),
  },

  character: {
    list: (projectId) => api._get('/api/characters', { projectId }),
    get: (id) => api._get(`/api/characters/${id}`),
    create: (data) => api._post('/api/characters', data),
    update: (id, fields) => api._put(`/api/characters/${id}`, fields),
    delete: (id) => api._delete(`/api/characters/${id}`),
    addField: (data) => api._post('/api/characters/fields', data),
    updateField: (fieldId, data) => api._put(`/api/characters/fields/${fieldId}`, data),
    removeField: (fieldId) => api._delete(`/api/characters/fields/${fieldId}`),
    reorderFields: (characterId, orderedIds) => api._post(`/api/characters/${characterId}/fields/reorder`, { orderedIds }),
    setAppearances: (characterId, appearances) => api._put(`/api/characters/${characterId}/appearances`, appearances),
  },

  worldSetting: {
    list: (projectId, category) => api._get('/api/world-settings', { projectId, category }),
    get: (id) => api._get(`/api/world-settings/${id}`),
    create: (data) => api._post('/api/world-settings', data),
    update: (id, fields) => api._put(`/api/world-settings/${id}`, fields),
    delete: (id) => api._delete(`/api/world-settings/${id}`),
  },

  inspiration: {
    list: (projectId, type, tag) => api._get('/api/inspirations', { projectId, type, tag }),
    get: (id) => api._get(`/api/inspirations/${id}`),
    create: (data) => api._post('/api/inspirations', data),
    update: (id, fields) => api._put(`/api/inspirations/${id}`, fields),
    delete: (id) => api._delete(`/api/inspirations/${id}`),
  },

  export: {
    toTxt: (params) => api._post('/api/export/txt', params),
    toDocx: (params) => api._post('/api/export/docx', params),
  },

  backup: {
    create: (backupPath) => api._post('/api/backup', { backupPath }),
    restore: (backupFilePath) => api._post('/api/backup/restore', { backupFilePath }),
    getInfo: (backupFilePath) => api._post('/api/backup/info', { backupFilePath }),
    getDbPath: () => api._get('/api/backup/db-path'),
  },

  recycle: {
    list: () => api._get('/api/recycle'),
    restore: (entityType, id) => api._post('/api/recycle/restore', { entityType, entityId: id }),
    permanentlyDelete: (entityType, id) => api._post('/api/recycle/permanent-delete', { entityType, entityId: id }),
    cleanExpired: () => api._post('/api/recycle/clean'),
  },

  search: {
    fullText: (projectId, keyword, types) => api._get('/api/search', { projectId, keyword, types: types?.join(',') }),
  },

  app: {
    getConfig: () => api._get('/api/config'),
    setConfig: (fields) => api._put('/api/config', fields),
  },
};
