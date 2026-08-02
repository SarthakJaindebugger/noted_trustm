// Configuration loader that works for both Vite dev server and static nginx build
class Config {
    constructor() {
        const placeholderDomain = "__VITE_DOMAIN__";
        let domain = placeholderDomain;
        let appBase = '/';
        let apiBaseUrl = '';
        let wsBaseUrl = '';

        // Vite populates import.meta.env at build/dev time
        if (typeof import.meta !== 'undefined' && import.meta.env) {
            if (typeof import.meta.env.VITE_DOMAIN === 'string' && import.meta.env.VITE_DOMAIN.trim() !== '') {
                domain = import.meta.env.VITE_DOMAIN.trim();
            }
            if (typeof import.meta.env.VITE_API_BASE_URL === 'string' && import.meta.env.VITE_API_BASE_URL.trim() !== '') {
                apiBaseUrl = import.meta.env.VITE_API_BASE_URL.trim();
            }
            if (typeof import.meta.env.VITE_WS_BASE_URL === 'string' && import.meta.env.VITE_WS_BASE_URL.trim() !== '') {
                wsBaseUrl = import.meta.env.VITE_WS_BASE_URL.trim();
            }
            if (typeof import.meta.env.BASE_URL === 'string' && import.meta.env.BASE_URL.trim() !== '') {
                appBase = import.meta.env.BASE_URL.trim();
            }
        }

        if ((placeholderDomain === "__VITE_DOMAIN__" || !placeholderDomain) &&
            typeof window !== 'undefined' && window.location && window.location.host) {
            domain = window.location.host;
        }

        this.domain = domain;
        this.apiBaseUrl = apiBaseUrl.replace(/\/+$|\s+$/g, '');
        this.wsBaseUrl = wsBaseUrl.replace(/\/+$|\s+$/g, '');

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
        if (this.apiBaseUrl) {
            return this.apiBaseUrl;
        }

        if (typeof window !== 'undefined' && window.location && window.location.origin) {
            return `${window.location.origin}${this.getBasePath()}/api`;
        }

        return `https://${this.domain}${this.getBasePath()}/api`;
    }

    getWebSocketBaseUrl() {
        if (this.wsBaseUrl) {
            return this.wsBaseUrl;
        }

        if (typeof window !== 'undefined' && window.location && window.location.host) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${protocol}//${window.location.host}${this.getBasePath()}`;
        }

        return `wss://${this.domain}${this.getBasePath()}`;
    }
}

export const config = new Config();
