import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';

export default {
name: 'AdminDashboard',

setup() {
    const router = useRouter();
    const searchQuery = ref('');

    const applications = ref([
        {
            id: 'APP-2024-456',
            name: 'Maria Garcia',
            priority: 'High',
            status: 'Pending Review',
            type: 'Work Permit',
            officer: 'Officer Chen',
            submitted: 'April 2, 2026'
        },
        {
            id: 'APP-2024-457',
            name: 'Ahmed Hassan',
            priority: 'Medium',
            status: 'Documents Required',
            type: 'Family Reunification',
            officer: 'Officer Martinez',
            submitted: 'April 2, 2026'
        },
        {
            id: 'APP-2024-458',
            name: 'Sophie Laurent',
            priority: 'Low',
            status: 'In Review',
            type: 'Student Visa',
            officer: 'Officer Johnson',
            submitted: 'April 1, 2026'
        },
        {
            id: 'APP-2024-459',
            name: 'Yuki Tanaka',
            priority: 'Low',
            status: 'Approved',
            type: 'Tourist Visa',
            officer: 'Officer Smith',
            submitted: 'March 31, 2026'
        },
        {
            id: 'APP-2024-460',
            name: 'Carlos Rodriguez',
            priority: 'High',
            status: 'Interview Scheduled',
            type: 'Permanent Residency',
            officer: 'Officer Brown',
            submitted: 'March 30, 2026'
        }
    ]);

    const logout = async () => {
        authService.logout();
        localStorage.removeItem('isAdmin');
        router.push({ name: 'login' });
    };

    return {
        searchQuery,
        applications,
        logout
    };
},

template: `
<div class="min-h-screen bg-gradient-to-br from-blue-50 via-white to-cyan-50">

    <!-- Header -->
    <div class="sticky top-0 z-10 backdrop-blur-md bg-white/60 border-b border-white/30">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">

            <div>
                <h1 class="text-3xl font-bold text-blue-900">
                    Admin Dashboard
                </h1>
                <p class="text-gray-600">
                    Comprehensive overview of immigration operations
                </p>
            </div>

            <button
                @click="logout"
                class="px-5 py-2 rounded-xl bg-red-500 text-white hover:bg-red-600 transition">
                Logout
            </button>

        </div>
    </div>

    <div class="max-w-7xl mx-auto p-6 space-y-8">

        <!-- Stats -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">

            <div class="glass-card p-6 rounded-2xl">
                <div class="text-gray-500">Total Applications</div>
                <div class="text-4xl font-bold mt-2">1,284</div>
                <div class="text-green-600 mt-2">+12.5% vs last month</div>
            </div>

            <div class="glass-card p-6 rounded-2xl">
                <div class="text-gray-500">Pending Review</div>
                <div class="text-4xl font-bold mt-2">342</div>
                <div class="text-green-600 mt-2">-8.2% vs last month</div>
            </div>

            <div class="glass-card p-6 rounded-2xl">
                <div class="text-gray-500">Approved Today</div>
                <div class="text-4xl font-bold mt-2">89</div>
                <div class="text-green-600 mt-2">+23.1% vs last month</div>
            </div>

            <div class="glass-card p-6 rounded-2xl">
                <div class="text-gray-500">Active Officers</div>
                <div class="text-4xl font-bold mt-2">24</div>
                <div class="text-green-600 mt-2">+2 vs last month</div>
            </div>

        </div>

        <!-- Charts Row -->
        <div class="grid lg:grid-cols-2 gap-6">

            <div class="glass-card rounded-2xl p-6">
                <h2 class="text-xl font-semibold mb-4">
                    Application Trends
                </h2>

                <div class="h-72 flex items-center justify-center text-gray-500">
                    Monthly application chart placeholder
                </div>
            </div>

            <div class="glass-card rounded-2xl p-6">
                <h2 class="text-xl font-semibold mb-4">
                    Applications by Type
                </h2>

                <div class="space-y-4">

                    <div>Work Permit: 30%</div>
                    <div>Tourist Visa: 22%</div>
                    <div>Student Visa: 15%</div>
                    <div>Family Reunification: 19%</div>
                    <div>Permanent Residency: 14%</div>

                </div>
            </div>

        </div>

        <!-- Tabs -->
        <div class="glass-card rounded-2xl p-4">
            <div class="flex gap-6">
                <button class="font-semibold text-blue-600">Applications</button>
                <button>Officers</button>
                <button>Performance</button>
                <button>Schedule</button>
            </div>
        </div>

        <!-- Applications Table -->
        <div class="glass-card rounded-2xl p-6">

            <div class="flex justify-between items-center mb-6">
                <div>
                    <h2 class="text-2xl font-semibold">
                        Recent Applications
                    </h2>
                    <p class="text-gray-500">
                        All applications requiring attention
                    </p>
                </div>

                <input
                    v-model="searchQuery"
                    placeholder="Search applications..."
                    class="px-4 py-2 rounded-xl border border-gray-200 w-72"
                />
            </div>

            <div class="space-y-4">

                <div
                    v-for="app in applications"
                    :key="app.id"
                    class="bg-white/50 backdrop-blur-md border border-white/30 rounded-2xl p-5">

                    <div class="flex justify-between items-start">

                        <div>

                            <div class="flex items-center gap-3">

                                <h3 class="font-semibold text-lg">
                                    {{ app.name }}
                                </h3>

                                <span
                                    class="px-3 py-1 rounded-full text-xs bg-red-100 text-red-700">
                                    {{ app.priority }}
                                </span>

                                <span
                                    class="px-3 py-1 rounded-full text-xs bg-blue-100 text-blue-700">
                                    {{ app.status }}
                                </span>

                            </div>

                            <div class="mt-3 text-gray-600">
                                ID: {{ app.id }}
                            </div>

                            <div class="text-gray-600">
                                Type: {{ app.type }}
                            </div>

                            <div class="text-gray-600">
                                Officer: {{ app.officer }}
                            </div>

                            <div class="text-gray-600">
                                Submitted: {{ app.submitted }}
                            </div>

                        </div>

                        <div class="flex gap-3">

                            <button
                                class="px-4 py-2 rounded-xl bg-blue-500 text-white">
                                Review
                            </button>

                            <button
                                class="px-4 py-2 rounded-xl bg-gray-200">
                                Assign
                            </button>

                        </div>

                    </div>

                </div>

            </div>

        </div>

    </div>
</div>
`

};