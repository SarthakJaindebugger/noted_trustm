import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';

export default {
    name: 'LoginView',
    setup() {
        const router = useRouter();
        const username = ref('');
        const password = ref('');
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
                const success = await authService.login(username.value, password.value);
                if (success) {
                    console.log('Login successful');
                    await router.push({ name: 'dashboard' });
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

        const handleKeyPress = (event) => {
            if (event.key === 'Enter') {
                handleLogin();
            }
        };

        return {
            username,
            password,
            isLoading,
            error,
            handleLogin,
            handleKeyPress
        };
    },
    template: `
        <div class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
            <div class="max-w-md w-full space-y-8">
                <!-- Logo and Header -->
                <div class="text-center">
                    <div class="mx-auto h-20 w-20 bg-gray-200 rounded-2xl flex items-center justify-center mb-6">
                        <div class="grid grid-cols-2 gap-1">
                            <div class="w-4 h-4 bg-gray-500 rounded-sm"></div>
                            <div class="w-4 h-4 bg-gray-400 rounded-full"></div>
                            <div class="w-4 h-4 bg-gray-400 rounded-full"></div>
                            <div class="w-4 h-4 bg-gray-500 rounded-sm"></div>
                        </div>
                    </div>
                    <h2 class="text-2xl font-bold text-gray-900 mb-2">
                        Welcome to Note'D! We're glad you're here.
                    </h2>
                    <p class="text-gray-600 text-sm mb-2">
                        Note'D helps you organise and remember important advice from<br>
                        Hello Espoo meetings.
                    </p>
                    <p class="text-gray-600 text-sm mb-2">
                        It's your tool for clear, translated summaries and reminders.
                    </p>
                    <p class="text-gray-600 text-sm">
                        Sign in to start using Note'D and make your next steps easier!
                    </p>
                </div>

                <!-- Login Form -->
                <div class="mt-8 space-y-6">
                    <div class="space-y-4">
                        <div>
                            <label for="username" class="sr-only">Username</label>
                            <input
                                id="username"
                                name="username"
                                type="text"
                                required
                                v-model="username"
                                @keypress="handleKeyPress"
                                class="relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                                placeholder="Username"
                            />
                        </div>
                        <div>
                            <label for="password" class="sr-only">Password</label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                required
                                v-model="password"
                                @keypress="handleKeyPress"
                                class="relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                                placeholder="Password"
                            />
                        </div>
                    </div>

                    <!-- Error Message -->
                    <div v-if="error" class="text-red-600 text-sm text-center">
                        {{ error }}
                    </div>

                    <!-- Login Button -->
                    <div>
                        <button
                            @click="handleLogin"
                            :disabled="isLoading"
                            class="group relative w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            <span v-if="!isLoading" class="flex items-center">
                                <svg class="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M5 3a2 2 0 00-2 2v.09A1.993 1.993 0 005 7v11a2 2 0 002 2h10a2 2 0 002-2V5a2 2 0 00-2-2H5zm4 8V9h6v2H9z"/>
                                </svg>
                                Sign in
                            </span>
                            <span v-else>Signing in...</span>
                        </button>
                    </div>

                    <!-- Learn More Link -->
                    <div class="text-center">
                        <a href="#" class="text-blue-600 hover:text-blue-500 text-sm underline">
                            Learn more about Note'd
                        </a>
                    </div>
                </div>
            </div>
        </div>
    `
};
