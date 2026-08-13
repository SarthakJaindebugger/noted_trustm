import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { languageService } from '../services/language_service.js';

export default {
    name: 'LoginView',
    setup() {
        const router = useRouter();
        const username = ref('');
        const password = ref('');
        const adminUsername = ref('');
        const adminPassword = ref('');
        const adminError = ref('');
        const adminLoading = ref(false);
        const isLoading = ref(false);
        const error = ref('');

        const handleLogin = async () => {
            if (!username.value || !password.value) {
                error.value = 'Please enter both username and password';
                return;
            }

            isLoading.value = true;
            error.value = '';

            try {
                const loggedInUser = await authService.login(username.value, password.value);
                if (loggedInUser?.role === 'user') {
                    console.log('Login successful');
                    localStorage.removeItem('isAdmin');
                    await router.push({ name: 'dashboard' });
                } else if (loggedInUser?.role === 'admin') {
                    authService.logout();
                    error.value = 'Please use the administrator login panel for admin accounts';
                } else {
                    error.value = 'Invalid credentials';
                }
            } catch (err) {
                error.value = 'Login failed. Please try again.';
                console.error('Login error:', err);
            } finally {
                isLoading.value = false;
            }
        };

        const handleAdminLogin = async () => {
    if (!adminUsername.value || !adminPassword.value) {
        adminError.value = 'Please enter both username and password';
        return;
    }

    adminLoading.value = true;
    adminError.value = '';

    try {
        const loggedInUser = await authService.login(
            adminUsername.value,
            adminPassword.value
        );

        if (loggedInUser?.role === 'admin') {
            console.log('Admin login successful');

            localStorage.setItem('isAdmin', 'true');

            await router.push({
                name: 'admin_dashboard'
            });
        } else if (loggedInUser?.role === 'user') {
            authService.logout();
            adminError.value = 'Please use the user login panel for user accounts';
        } else {
            adminError.value = 'Invalid admin credentials';
        }
    } catch (err) {
        adminError.value = 'Admin login failed';
        console.error(err);
    } finally {
        adminLoading.value = false;
    }
        };

        const handleKeyPress = (event) => {
            if (event.key === 'Enter') {
                handleLogin();
            }
        };

        // Glassmorphism styles injection
        const injectGlassStyles = () => {
            if (document.getElementById('login-glass-styles')) return;
            
            const styleEl = document.createElement('style');
            styleEl.id = 'login-glass-styles';
            styleEl.textContent = `
                /* Glassmorphism Base */
                .glass-login {
                    background: linear-gradient(135deg, #eef2ff 0%, #ffffff 40%, #f0f9ff 100%);
                    min-height: 100vh;
                }
                
                /* Glass Card Effect */
                .glass-card {
                    background: rgba(255, 255, 255, 0.65) !important;
                    backdrop-filter: blur(12px) !important;
                    border: 1px solid rgba(255, 255, 255, 0.4) !important;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08) !important;
                    transition: all 0.3s ease;
                }
                
                .glass-card:hover {
                    transform: translateY(-4px);
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12);
                    background: rgba(255, 255, 255, 0.75) !important;
                }
                
                /* Input fields glass */
                .glass-input {
                    background: rgba(255, 255, 255, 0.8) !important;
                    border: 1px solid rgba(59, 130, 246, 0.3) !important;
                    backdrop-filter: blur(4px);
                    transition: all 0.2s;
                }
                
                .glass-input:focus {
                    border-color: #3b82f6 !important;
                    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2) !important;
                    background: rgba(255, 255, 255, 0.95) !important;
                }
                
                /* Primary button gradient */
                .btn-primary {
                    background: linear-gradient(105deg, #2563eb, #3b82f6, #60a5fa) !important;
                    background-size: 200% auto;
                    border: none;
                    transition: all 0.3s ease;
                    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
                }
                
                .btn-primary:hover:not(:disabled) {
                    background-position: right center;
                    transform: translateY(-2px);
                    box-shadow: 0 8px 20px rgba(37, 99, 235, 0.3);
                }
                
                .btn-primary:disabled {
                    opacity: 0.6;
                    cursor: not-allowed;
                }
                
                /* Admin card button (disabled) */
                .btn-admin {
                    background: rgba(100, 116, 139, 0.8);
                    backdrop-filter: blur(4px);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    cursor: not-allowed;
                }
                
                /* Headings glass text */
                .glass-heading {
                    background: linear-gradient(135deg, #1e3a8a, #3b82f6);
                    -webkit-background-clip: text;
                    background-clip: text;
                    color: transparent;
                    font-weight: 600;
                }
                
                /* Link style */
                .glass-link {
                    color: #3b82f6;
                    transition: all 0.2s;
                }
                
                .glass-link:hover {
                    color: #2563eb;
                    text-shadow: 0 0 4px rgba(59, 130, 246, 0.3);
                }
            `;
            document.head.appendChild(styleEl);
        };

        onMounted(() => {
            injectGlassStyles();
        });

        onUnmounted(() => {
            const styleEl = document.getElementById('login-glass-styles');
            if (styleEl) styleEl.remove();
        });

        
        const showLangDropdown = ref(false);
        const languages = languageService.LANGUAGES;
        const currentLanguage = languageService.currentLanguage;
        const changeLanguage = async (code) => {
            showLangDropdown.value = false;
            await languageService.setLanguage(code);
        };
        const getLanguageLabel = languageService.getLanguageLabel;

        return {
        username,
        password,
        isLoading,
        error,
        handleLogin,

        adminUsername,
        adminPassword,
        adminLoading,
        adminError,
        handleAdminLogin,

        handleKeyPress,
        showLangDropdown,
        languages,
        currentLanguage,
        changeLanguage,
        getLanguageLabel,
    };


    },
    template: `
        <div class="glass-login flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8 relative">
            <!-- Language Selector -->
            <div class="absolute top-4 right-6 z-20 notranslate" translate="no">
              <div class="relative">
                <button @click="showLangDropdown = !showLangDropdown"
                  class="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/70 backdrop-blur border border-gray-200 text-sm font-medium text-gray-700 hover:bg-white/90 transition shadow-sm">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"/></svg>
                  {{ getLanguageLabel() }}
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
                </button>
                <div v-if="showLangDropdown" class="absolute right-0 mt-2 w-44 bg-white rounded-xl shadow-lg border border-gray-100 py-1 max-h-64 overflow-y-auto z-30">
                  <button v-for="lang in languages" :key="lang.code"
                    @click="changeLanguage(lang.code)"
                    :class="['w-full text-left px-4 py-2 text-sm hover:bg-blue-50 transition', currentLanguage === lang.code ? 'text-blue-600 font-medium bg-blue-50/50' : 'text-gray-700']">
                    {{ lang.label }}
                  </button>
                </div>
              </div>
            </div>

            <div class="max-w-6xl w-full space-y-10">
                <!-- Header Section -->
                <div class="text-center">
                    <div class="mx-auto h-20 w-20 bg-white/40 backdrop-blur rounded-2xl flex items-center justify-center mb-6 shadow-lg border border-white/30">
                        <div class="grid grid-cols-2 gap-1">
                            <div class="w-4 h-4 bg-blue-500 rounded-sm"></div>
                            <div class="w-4 h-4 bg-blue-400 rounded-full"></div>
                            <div class="w-4 h-4 bg-blue-400 rounded-full"></div>
                            <div class="w-4 h-4 bg-blue-500 rounded-sm"></div>
                        </div>
                    </div>
                    <h2 class="text-3xl font-bold glass-heading mb-3">
                        Welcome to Note'D
                    </h2>
                    <p class="text-gray-700 text-base max-w-2xl mx-auto">
                        Note'D helps you organise and remember important advice from Hello Espoo meetings.
                        It's your tool for clear, translated summaries and reminders.
                    </p>
                </div>

                <!-- Two Glass Cards: User & Admin -->
                <div class="grid md:grid-cols-2 gap-8">
                    <!-- User Login Card -->
                    <div class="glass-card rounded-2xl p-8 space-y-6">
                        <div class="text-center">
                            <h3 class="text-xl font-semibold text-gray-800">User Access</h3>
                            <p class="text-sm text-gray-600 mt-1">Sign in to your personal dashboard</p>
                        </div>

                        <div class="space-y-5">
                            <div>
                                <label for="username" class="block text-sm font-medium text-gray-700 mb-1">Username</label>
                                <input
                                    id="username"
                                    name="username"
                                    type="text"
                                    required
                                    v-model="username"
                                    @keypress="handleKeyPress"
                                    class="glass-input relative block w-full px-4 py-3 text-gray-900 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                    placeholder="Enter your username"
                                />
                            </div>
                            <div>
                                <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                                <input
                                    id="password"
                                    name="password"
                                    type="password"
                                    required
                                    v-model="password"
                                    @keypress="handleKeyPress"
                                    class="glass-input relative block w-full px-4 py-3 text-gray-900 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                    placeholder="Enter your password"
                                />
                            </div>

                            <!-- Error Message -->
                            <div v-if="error" class="text-red-600 text-sm text-center bg-red-50/50 rounded-lg py-2">
                                {{ error }}
                            </div>

                            <!-- Login Button -->
                            <button
                                @click="handleLogin"
                                :disabled="isLoading"
                                class="btn-primary group relative w-full flex justify-center py-3 px-4 text-sm font-medium rounded-xl text-white transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                            >
                                <span v-if="!isLoading" class="flex items-center">
                                    <svg class="w-5 h-5 mr-2" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M5 3a2 2 0 00-2 2v.09A1.993 1.993 0 005 7v11a2 2 0 002 2h10a2 2 0 002-2V5a2 2 0 00-2-2H5zm4 8V9h6v2H9z"/>
                                    </svg>
                                    Sign in
                                </span>
                                <span v-else>Signing in...</span>
                            </button>
                        </div>
                    </div>

                    <!-- Admin Login Card -->
                    <div class="glass-card rounded-2xl p-8 space-y-6">
                        <div class="text-center">
                            <h3 class="text-xl font-semibold text-gray-800">
                                Administrator Access
                            </h3>
                            <p class="text-sm text-gray-600 mt-1">
                                Secure portal for platform management
                            </p>
                        </div>

                        <div class="space-y-5">

                            <div>
                                <label
                                    class="block text-sm font-medium text-gray-700 mb-1">
                                    Admin Username
                                </label>

                                <input
                                    type="text"
                                    v-model="adminUsername"
                                    class="glass-input relative block w-full px-4 py-3 text-gray-900 rounded-xl"
                                    placeholder="Enter admin username"
                                />
                            </div>

                            <div>
                                <label
                                    class="block text-sm font-medium text-gray-700 mb-1">
                                    Admin Password
                                </label>

                                <input
                                    type="password"
                                    v-model="adminPassword"
                                    class="glass-input relative block w-full px-4 py-3 text-gray-900 rounded-xl"
                                    placeholder="Enter admin password"
                                />
                            </div>

                            <div
                                v-if="adminError"
                                class="text-red-600 text-sm text-center bg-red-50/50 rounded-lg py-2">
                                {{ adminError }}
                            </div>

                            <button
                                @click="handleAdminLogin"
                                :disabled="adminLoading"
                                class="btn-primary group relative w-full flex justify-center py-3 px-4 text-sm font-medium rounded-xl text-white">

                                <span v-if="!adminLoading">
                                    Login
                                </span>

                                <span v-else>
                                    Signing in...
                                </span>
                            </button>

                            
                        </div>
                    </div>
                    
                </div>

                <!-- Footer Link -->
                <div class="text-center pt-4">
                    <a href="#" class="glass-link text-sm underline">Learn more about Note'd</a>
                </div>
            </div>
        </div>
    `
};