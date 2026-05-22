/**
 * Main entry point for the frontend application.
 */

import { createApp } from 'vue';
import { createPinia } from 'pinia';
import router from './router.js';
import { useAuthStore } from './stores/auth.js';

// Root App component — just a router-view now
const App = {
    name: 'App',
    template: `
        <div id="app">
            <router-view />
        </div>
    `,
};

// Create and configure the app
const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);

// Initialize auth store and check auth state
const authStore = useAuthStore();
authStore.checkAuth();

// Mount
app.mount('#app');

// Debug helper
window.clearAuth = () => {
    authStore.logout();
    router.push('/login');
    console.log('Authentication cleared');
};
