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

    async switchRole(newRole) {
        if (this.user) {
            if (this.user.role === 'admin' && newRole === 'user') {
                this.user = {
                    ...this.user,
                    role: 'user',
                    username: 'demo',
                    _actingAs: true,
                    _originalToken: this.token,
                };
                sessionStorage.setItem('user', JSON.stringify(this.user));
                return;
            }
            if (newRole === 'admin') {
                // Restore original admin token if available, otherwise re-login as admin
                if (this.user._originalToken) {
                    this.token = this.user._originalToken;
                    sessionStorage.setItem('auth_token', this.token);
                    this.user.role = 'admin';
                    this.user.username = 'admin';
                    delete this.user._actingAs;
                    delete this.user._originalToken;
                    sessionStorage.setItem('user', JSON.stringify(this.user));
                } else {
                    // Login as admin to get a valid admin token
                    await this.login('admin', 'admin');
                }
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
