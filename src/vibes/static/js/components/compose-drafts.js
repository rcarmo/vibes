// Persist text/reference metadata only. File objects remain page-local.
export function draftKey(sessionId) {
    return `vibes_compose_draft:${encodeURIComponent(sessionId)}`;
}

export class ComposeDrafts {
    constructor(storage) {
        this.storage = storage;
        this.files = new Map();
    }

    load(sessionId) {
        let data = {};
        try { data = JSON.parse(this.storage.getItem(draftKey(sessionId)) || '{}') || {}; } catch { /* Unavailable storage. */ }
        const refs = key => Array.isArray(data[key]) ? data[key].filter(x => typeof x === 'string').slice(0, 100) : [];
        return {
            text: typeof data.text === 'string' ? data.text.slice(0, 100000) : '',
            fileRefs: refs('fileRefs'), folderRefs: refs('folderRefs'), messageRefs: refs('messageRefs'),
            files: [...(this.files.get(sessionId) || [])],
        };
    }

    save(sessionId, draft) {
        const strings = values => Array.isArray(values) ? values.filter(x => typeof x === 'string').slice(0, 100) : [];
        const data = {
            text: typeof draft.text === 'string' ? draft.text.slice(0, 100000) : '',
            fileRefs: strings(draft.fileRefs), folderRefs: strings(draft.folderRefs), messageRefs: strings(draft.messageRefs),
        };
        if (draft.files?.length) this.files.set(sessionId, [...draft.files]);
        else this.files.delete(sessionId);
        try { this.storage.setItem(draftKey(sessionId), JSON.stringify(data)); } catch { /* Quota/private mode. */ }
    }

    clear(sessionId) {
        this.files.delete(sessionId);
        try { this.storage.removeItem(draftKey(sessionId)); } catch { /* Unavailable storage. */ }
    }
}

// Shared page-local File storage survives component remounts. Access localStorage
// lazily so privacy-mode access errors are caught by ComposeDrafts methods.
export const composeDrafts = new ComposeDrafts({
    getItem: key => window.localStorage.getItem(key),
    setItem: (key, value) => window.localStorage.setItem(key, value),
    removeItem: key => window.localStorage.removeItem(key),
});
