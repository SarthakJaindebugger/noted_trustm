export default {
    name: 'FAQPage',
    setup() {
        return {};
    },
    template: `
        <div class="glass-dashboard min-h-screen flex flex-col">
            <!-- Header (simple, consistent style) -->
            <header class="bg-white border-b border-gray-200 px-6 py-4">
                <div class="flex items-center justify-between">
                    <h1 class="text-xl font-semibold text-gray-900">Note'd FAQs</h1>
                    <router-link
                        to="/dashboard"
                        class="flex items-center space-x-2 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                        </svg>
                        <span>Back to Dashboard</span>
                    </router-link>
                </div>
            </header>

            <!-- FAQ Content -->
            <main class="flex-1 px-6 py-8">
                <div class="max-w-4xl mx-auto space-y-6">
                    <div class="bg-white/70 backdrop-blur-xl border border-gray-200 rounded-xl p-6 shadow-sm">
                        <h2 class="text-lg font-semibold text-gray-900 mb-2">What is Note'd?</h2>
                        <p class="text-gray-700 text-sm leading-relaxed">
                            Note'd is your AI‑powered session assistant. It records, transcribes, and summarises your meetings,
                            saving you time and making information easy to revisit.
                        </p>
                    </div>

                    <div class="bg-white/70 backdrop-blur-xl border border-gray-200 rounded-xl p-6 shadow-sm">
                        <h2 class="text-lg font-semibold text-gray-900 mb-2">How do I start a new session?</h2>
                        <p class="text-gray-700 text-sm leading-relaxed">
                            Click the <strong>New Session</strong> button on the dashboard. Your session will begin immediately
                            and you can start recording or typing notes right away.
                        </p>
                    </div>

                    <div class="bg-white/70 backdrop-blur-xl border border-gray-200 rounded-xl p-6 shadow-sm">
                        <h2 class="text-lg font-semibold text-gray-900 mb-2">How do I view my session summary?</h2>
                        <p class="text-gray-700 text-sm leading-relaxed">
                            Click on any session row in the sessions list. This opens the detailed view with topics,
                            an overview, and transcripts (if available). You can also export a PDF from there.
                        </p>
                    </div>

                    <div class="bg-white/70 backdrop-blur-xl border border-gray-200 rounded-xl p-6 shadow-sm">
                        <h2 class="text-lg font-semibold text-gray-900 mb-2">Can I edit transcripts or notes?</h2>
                        <p class="text-gray-700 text-sm leading-relaxed">
                            Yes! In the session details view you can edit the session overview, advisor notes, and even
                            individual transcript entries. All changes are saved automatically.
                        </p>
                    </div>
                </div>
            </main>
        </div>
    `,
};