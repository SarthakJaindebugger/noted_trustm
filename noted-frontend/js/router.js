/**
 * Vue Router — replaces manual currentView switching.
 *
 * During migration, components still export plain objects with template strings.
 * Vue Router handles them fine — they don't need to be SFCs.
 */

import { createRouter, createWebHistory } from 'vue-router';
import { authService } from './services/auth_service.js';

// Import components (they export default objects)
import LoginView from './components/login_component.js';
import Dashboard from './components/dashboard.js';
import NewSession from './components/new_session.js';
import RecordingView from './components/recording_view.js';
import ExperimentView from './components/experiment_view.js';
import AdminDashboard from './components/admin_dashboard.js';


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
];

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes,
});

// Auth guard
router.beforeEach((to, from, next) => {
    const needsAuth = to.name !== 'login';

    if (needsAuth && !authService.isAuthenticated()) {
        next({ name: 'login' });
    } else if (to.name === 'login' && authService.isAuthenticated()) {
        next({ name: 'dashboard' });
    } else {
        next();
    }
});

export default router;
