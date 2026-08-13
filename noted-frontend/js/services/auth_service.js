import { apiClient } from './api_client.js';

class AuthService {
    constructor() {
        this.token = sessionStorage.getItem('auth_token');
        this.user = JSON.parse(sessionStorage.getItem('user') || 'null');
    }

    async login(username, password) {
        try {
            const data = await apiClient.post('/auth/login', { username, password }, {
                skipAuth: true,
            });
            this.token = data.access_token;
            this.user = data.user;

            sessionStorage.setItem('auth_token', this.token);
            sessionStorage.setItem('user', JSON.stringify(this.user));

            return this.user;
        } catch (error) {
            console.error('Login error:', error);
            return false;
        }
    }

    logout() {
        this.token = null;
        this.user = null;
        sessionStorage.removeItem('auth_token');
        sessionStorage.removeItem('user');
        localStorage.removeItem('isAdmin');
    }

    isAuthenticated() {
        return !!this.token;
    }

    getUser() {
        return this.user;
    }

    isAdmin() {
        return this.user?.role === 'admin';
    }

    switchRole(newRole) {
        if (this.user) {
            if (this.user.role === 'admin' && newRole === 'user') {
                this.user = {
                    ...this.user,
                    role: 'user',
                    username: 'demo',
                    _actingAs: true,
                };
                sessionStorage.setItem('user', JSON.stringify(this.user));
                return;
            }
            if (this.user.role === 'user' && newRole === 'admin') {
                this.user.role = 'admin';
                delete this.user._actingAs;
                sessionStorage.setItem('user', JSON.stringify(this.user));
                return;
            }
            this.user.role = newRole;
            sessionStorage.setItem('user', JSON.stringify(this.user));
        }
    }

    getToken() {
        return this.token;
    }

    getAuthHeaders() {
        const headers = {
            'Authorization': `Bearer ${this.token}`,
            'Content-Type': 'application/json',
        };
        if (this.user && this.user._actingAs) {
            headers['X-Acting-As'] = this.user.username;
        }
        return headers;
    }
}

export const authService = new AuthService();
