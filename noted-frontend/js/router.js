/**
 * Vue Router — replaces manual currentView switching.
 *
 * During migration, components still export plain objects with template strings.
 * Vue Router handles them fine — they don't need to be SFCs.
 */

import { createRouter, createWebHashHistory } from 'vue-router';
import { authService } from './services/auth_service.js';

// Import components (they export default objects)
import LoginView from './components/login_component.js';
import Dashboard from './components/dashboard.js';
import NewSession from './components/new_session.js';
import RecordingView from './components/recording_view.js';
import ExperimentView from './components/experiment_view.js';
import AdminDashboard from './components/admin_dashboard.js';
import FileBrowserView from './components/file_browser_component.js';


const routes = [
    {
        path: '/',
        redirect: '/login',
    },
    {
        path: '/login',
        name: 'login',
        component: LoginView,
    },
    {
        path: '/dashboard',
        name: 'dashboard',
        component: Dashboard,
    },
    {
        path: '/session/:sessionId',
        name: 'session-detail',
        component: Dashboard,
        props: true,
    },
    {
        path: '/new-session',
        name: 'new-session',
        component: NewSession,
    },
    {
        path: '/admin',
        name: 'admin_dashboard',
        component: AdminDashboard
    },
    {
        path: '/admin/files',
        name: 'admin_files',
        component: FileBrowserView
    },
    {
        path: '/record/:sessionId?',
        name: 'recording',
        component: RecordingView,
        props: true,
    },
    {
        path: '/experiment/:sessionId?',
        name: 'experiment',
        component: ExperimentView,
        props: true,
    },
    {
        path: '/crm/:sessionId',
        name: 'crm-form',
        component: () => import('./components/crm_form.js').then(m => m.default),
        props: true,
    },
    {
        path: '/:pathMatch(.*)*',
        redirect: '/login',
    },
];

const router = createRouter({
    history: createWebHashHistory(),
    routes,
});

// Auth guard
router.beforeEach((to, from, next) => {
    const needsAuth = to.name !== 'login';
    const adminOnly = ['admin_dashboard', 'admin_files'];

    if (needsAuth && !authService.isAuthenticated()) {
        next({ name: 'login' });
    } else if (adminOnly.includes(to.name) && !authService.isAdmin()) {
        next({ name: 'dashboard' });
    } else if (to.name === 'login' && authService.isAuthenticated()) {
        // If user is logged in and navigates back to login, log them out
        authService.logout();
        next();
    } else {
        next();
    }
});

export default router;
