// Configuration loader that works for both Vite dev server and static nginx build
class Config {
    constructor() {
        const placeholderDomain = "__VITE_DOMAIN__";
        let domain = placeholderDomain;
        let appBase = '/';

        // Vite populates import.meta.env at build/dev time
        if (typeof import.meta !== 'undefined' &&
            import.meta.env &&
            typeof import.meta.env.VITE_DOMAIN === 'string' &&
            import.meta.env.VITE_DOMAIN.trim() !== '') {
            domain = import.meta.env.VITE_DOMAIN.trim();
        } else if (placeholderDomain === "__VITE_DOMAIN__" || !placeholderDomain) {
            // In production the Docker image replaces the placeholder; fall back to host if it did not
            if (typeof window !== 'undefined' && window.location && window.location.host) {
                domain = window.location.host;
            } else {
                domain = 'localhost';
            }
        }

        this.domain = domain;

        if (typeof import.meta !== 'undefined' &&
            import.meta.env &&
            typeof import.meta.env.BASE_URL === 'string' &&
            import.meta.env.BASE_URL.trim() !== '') {
            appBase = import.meta.env.BASE_URL.trim();
        }

        if (!appBase.startsWith('/')) {
            appBase = `/${appBase}`;
        }

        if (!appBase.endsWith('/')) {
            appBase = `${appBase}/`;
        }

        this.appBase = appBase;
    }

    getBasePath() {
        return this.appBase === '/' ? '' : this.appBase.replace(/\/$/, '');
    }

    getApiBaseUrl() {
        if (typeof window !== 'undefined' && window.location && window.location.origin) {
            return `${window.location.origin}${this.getBasePath()}/api`;
        }

        return `https://${this.domain}${this.getBasePath()}/api`;
    }

    getWebSocketBaseUrl() {
        if (typeof window !== 'undefined' && window.location && window.location.host) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${protocol}//${window.location.host}${this.getBasePath()}`;
        }

        return `wss://${this.domain}${this.getBasePath()}`;
    }
}

export const config = new Config();
