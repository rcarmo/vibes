// Resolve a switch before committing UI state; late responses never win.
export class SessionNavigation {
    constructor({ loadTimeline, drafts, commit }) {
        this.loadTimeline = loadTimeline;
        this.drafts = drafts;
        this.commit = commit;
        this.generation = 0;
        this.disposed = false;
    }

    async select(sessionId) {
        if (this.disposed) return false;
        const generation = ++this.generation;
        let result;
        try { result = await this.loadTimeline(sessionId); }
        catch (error) {
            if (generation !== this.generation || this.disposed) return false;
            throw error;
        }
        if (generation !== this.generation || this.disposed) return false;
        if (!result || !Array.isArray(result.posts)) throw new Error('Invalid session timeline');
        const draft = this.drafts.load(sessionId);
        this.commit({ sessionId, posts: result.posts, hasMore: !!result.has_more, draft });
        return true;
    }

    dispose() {
        this.disposed = true;
        this.generation++;
    }
}
