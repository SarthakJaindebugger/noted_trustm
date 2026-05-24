import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { useDashboardSessions } from '../composables/use_dashboard_sessions.js';
import { useDashboardSessionActions } from '../composables/use_dashboard_session_actions.js';
import { useDashboardExports } from '../composables/use_dashboard_exports.js';
import { useSessionDetail } from '../composables/use_session_detail.js';
import { formatSecondsTimestamp as formatTimestamp } from '../utils/text.js';
import StatusBadge, { getStatusDisplay, isProcessingStatus } from './ui/status_badge.js';
import NotificationModal from './ui/notification_modal.js';
import BaseModal from './ui/base_modal.js';
import TopicCard from './topic_card.js';
import TranscriptViewer from './transcript_viewer.js';

export default {
    name: 'Dashboard',
    components: { StatusBadge, NotificationModal, BaseModal, TopicCard, TranscriptViewer },
    setup() {
        const route = useRoute();
        const user = ref(authService.getUser());
        const {
            sessions,
            sessionsById,
            sessionsByReference,
            filteredSessions,
            searchQuery,
            selectedSessions,
            itemsPerPage,
            pageSizeOptions,
            currentPage,
            paginatedSessions,
            totalPages,
            pageDisplayRange,
            visibleSelectionState,
            isLoading,
            sortField,
            sortDirection,
            showDropdownId,
            currentView,
            selectedSession,
            selectedSessionRef,
            selectedSessionDbId,
            pendingSessionToOpen,
            isOpeningSession,
            resolveSession,
            setSelectedSession,
            filterSessions,
            applySessionUpdate,
            searchSessions,
            sortBy,
            toggleDropdown,
            closeDropdown,
            toggleSessionSelection,
            selectAllSessions,
            goToPage,
            goToFirstPage,
            goToLastPage,
            nextPage,
            prevPage,
            loadSessions,
        } = useDashboardSessions();
        const showNotificationModal = ref(false);
        const notificationTitle = ref('');
        const notificationMessage = ref('');
        const notificationType = ref('success'); // 'success', 'error', 'info'

        // getStatusDisplay and isProcessingStatus imported from ui/status_badge.js

        const attemptOpenPendingSession = async () => {
            if (!pendingSessionToOpen.value) {
                return;
            }

            const session = resolveSession(pendingSessionToOpen.value);
            if (!session) {
                return;
            }

            pendingSessionToOpen.value = null;

            try {
                await showSessionDetails(session, false);
            } finally {
                isOpeningSession.value = false;
            }
        };

        // Modal management functions
        const showNotification = (title, message, type = 'info') => {
            notificationTitle.value = title;
            notificationMessage.value = message;
            notificationType.value = type;
            showNotificationModal.value = true;
        };

        const closeNotificationModal = () => {
            showNotificationModal.value = false;
            notificationTitle.value = '';
            notificationMessage.value = '';
        };

        const {
            topics,
            sessionSummary,
            overviewText,
            loadingTopics,
            selectedLanguage,
            availableLanguages,
            isEditingOverview,
            editingOverviewText,
            savingOverview,
            advisorNotes,
            isEditingNotes,
            notesBeingEdited,
            savingNotes,
            showAddTopicPopup,
            newTopicReference,
            generatingTopic,
            editingTopic,
            editingTopicDraft,
            showTranscript,
            transcriptData,
            loadingTranscript,
            editingTranscript,
            editedTranscriptEntries,
            translatedLanguage,
            startEditingOverview,
            cancelEditingOverview,
            saveOverview,
            loadSessionSummary,
            toggleTopic,
            deleteTopic,
            addTopic,
            showAddTopicDialog,
            closeAddTopicPopup,
            generateNewTopic,
            startEditingTopic,
            saveTopicEdit,
            finalizeTopicEdit,
            cancelTopicEdit,
            startEditingNotes,
            cancelEditingNotes,
            saveAdvisorNotes,
            viewTranscript,
            closeTranscript,
            startEditingTranscript,
            saveTranscriptChanges,
            cancelTranscriptEdit,
            applyTranslationToView,
            translateCurrentSummary,
        } = useSessionDetail({
            selectedSession,
            selectedSessionDbId,
            selectedSessionRef,
            showNotification,
        });

        const {
            isEditingSessionName,
            editedSessionName,
            isSavingSessionName,
            canEditSessionName,
            showCRMPopup,
            showFinishSessionPopup,
            showConfirmModal,
            confirmModalMessage,
            syncEditedSessionName,
            confirmAction,
            cancelConfirm,
            openCRMForm,
            closeCRMPopup,
            deleteSessionFromPopup,
            saveAsDraft,
            continueEditing,
            showFinishSessionDialog,
            closeFinishSessionPopup,
            deleteSessionFromFinishPopup,
            saveSession,
            saveAndEditSummary,
            deleteSession,
            showSessionDetails,
            showSessionsList,
            openSession,
            resumeSession,
            viewPDF,
            startNewSession,
            launchExperiment,
            openCRMFormPage,
            bulkDeleteSessions,
            startEditingSessionName,
            cancelSessionNameEdit,
            saveSessionNameEdit,
            logout,
        } = useDashboardSessionActions({
            selectedSession,
            selectedSessionRef,
            selectedSessionDbId,
            currentView,
            pendingSessionToOpen,
            isOpeningSession,
            selectedSessions,
            sessionsById,
            isLoading,
            setSelectedSession,
            closeDropdown,
            loadSessions,
            loadSessionSummary,
            applySessionUpdate,
            finalizeTopicEdit,
            showNotification,
        });

        watch(selectedSession, () => {
            syncEditedSessionName();
        });

        const {
            showPdfPreviewModal,
            pdfPreviewUrl,
            isGeneratingPdf,
            previewPDF,
            downloadPDF,
            downloadSessionData,
            closePdfPreviewModal,
        } = useDashboardExports({
            selectedSessionRef,
            topics,
            sessionSummary,
            translatedLanguage,
            selectedLanguage,
            showNotification,
        });

        // Handle opening session details from external events
        const handleOpenSessionDetails = async (event) => {
            const { sessionId } = event.detail;
            if (!sessionId) {
                return;
            }

            pendingSessionToOpen.value = sessionId;
            isOpeningSession.value = true;
            await attemptOpenPendingSession();
        };

        const openRouteSessionIfNeeded = async () => {
            const routeSessionId = route.params.sessionId;
            if (route.name !== 'session-detail' || !routeSessionId) {
                if (route.name === 'dashboard') {
                    currentView.value = 'sessions-list';
                }
                return;
            }

            pendingSessionToOpen.value = String(routeSessionId);
            isOpeningSession.value = true;
            await attemptOpenPendingSession();
        };

        // Load sessions on component mount
        onMounted(async () => {
            await loadSessions();
            await attemptOpenPendingSession();
            await openRouteSessionIfNeeded();
            
            // Listen for requests to open session details
            window.addEventListener('open-session-details', handleOpenSessionDetails);
        });

        // Cleanup event listener
        onUnmounted(() => {
            window.removeEventListener('open-session-details', handleOpenSessionDetails);
        });

        watch(
            () => route.fullPath,
            async () => {
                await openRouteSessionIfNeeded();
            }
        );


        return {
            sessions,
            sessionsById,
            sessionsByReference,
            filteredSessions,
            paginatedSessions,
            searchQuery,
            selectedSessions,
            itemsPerPage,
            pageSizeOptions,
            currentPage,
            totalPages,
            pageDisplayRange,
            user,
            isLoading,
            currentView,
            selectedSession,
            selectedSessionRef,
            selectedSessionDbId,
            isEditingSessionName,
            editedSessionName,
            isSavingSessionName,
            canEditSessionName,
            topics,
            sessionSummary,
            overviewText,
            isEditingOverview,
            editingOverviewText,
            savingOverview,
            startEditingOverview,
            cancelEditingOverview,
            saveOverview,
            loadingTopics,
            isGeneratingPdf,
            selectedLanguage,
            availableLanguages,
            showCRMPopup,
            showFinishSessionPopup,
            showConfirmModal,
            confirmModalMessage,
            confirmAction,
            cancelConfirm,
            advisorNotes,
            isEditingNotes,
            notesBeingEdited,
            savingNotes,
            filterSessions,
            searchSessions,
            toggleSessionSelection,
            selectAllSessions,
            visibleSelectionState,
            goToPage,
            goToFirstPage,
            goToLastPage,
            nextPage,
            prevPage,
            startNewSession,
            launchExperiment,
            openCRMFormPage,
            bulkDeleteSessions,
            isOpeningSession,
            startEditingSessionName,
            cancelSessionNameEdit,
            saveSessionNameEdit,
            logout,
            loadSessionSummary,
            showSessionDetails,
            showSessionsList,
            toggleTopic,
            deleteTopic,
            addTopic,
            showAddTopicPopup,
            newTopicReference,
            generatingTopic,
            showAddTopicDialog,
            closeAddTopicPopup,
            generateNewTopic,
            editingTopic,
            editingTopicDraft,
            startEditingTopic,
            saveTopicEdit,
            cancelTopicEdit,
            startEditingNotes,
            cancelEditingNotes,
            saveAdvisorNotes,
            viewTranscript,
            closeTranscript,
            startEditingTranscript,
            saveTranscriptChanges,
            cancelTranscriptEdit,
            formatTimestamp,
            showTranscript,
            transcriptData,
            loadingTranscript,
            editingTranscript,
            editedTranscriptEntries,
            previewPDF,
            downloadPDF,
            downloadSessionData,
            sortField,
            sortDirection,
            sortBy,
            showDropdownId,
            toggleDropdown,
            closeDropdown,
            openCRMForm,
            closeCRMPopup,
            deleteSessionFromPopup,
            saveAsDraft,
            continueEditing,
            showFinishSessionDialog,
            closeFinishSessionPopup,
            deleteSessionFromFinishPopup,
            saveSession,
            saveAndEditSummary,
            openSession,
            resumeSession,
            viewPDF,
            deleteSession,
            showNotificationModal,
            notificationTitle,
            notificationMessage,
            notificationType,
            closeNotificationModal,
            showPdfPreviewModal,
            pdfPreviewUrl,
            closePdfPreviewModal,
            applyTranslationToView,
            translateCurrentSummary,
            setSelectedSession,
            resolveSession,
            getStatusDisplay,
            isProcessingStatus,
            loadSessions
        };
    },
    template: `
        <div class="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-slate-100" @click="closeDropdown">
            <!-- Header -->
            <header class="sticky top-0 z-40 border-b border-white/20 bg-white/10 backdrop-blur-xl px-6 py-4 shadow-lg shadow-black/10">
                <div class="flex items-center justify-between">
                    <div>
                        <h1 class="text-xl font-semibold text-white">Note'D</h1>
                        <p class="text-sm text-slate-200">Helps you organise and remember important advice from Hello Espoo meetings.</p>
                    </div>
                    
                    <!-- User Menu -->
                    <div class="flex items-center space-x-4">
                        <div class="flex items-center space-x-2">
                            <div class="w-9 h-9 bg-indigo-500/80 rounded-full ring-2 ring-indigo-300/50 flex items-center justify-center shadow-md">
                                <span class="text-white text-sm font-semibold">
                                    {{ user?.name?.charAt(0) || 'U' }}
                                </span>
                            </div>
                            <div class="relative">
                                <button @click="logout" class="px-3 py-2 text-sm rounded-xl border border-white/30 bg-white/10 hover:bg-white/20 text-slate-100 transition-all">
                                    Logout
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            <!-- Main Content -->
            <main class="px-6 py-6">
                <!-- Sessions List View -->
                <div v-if="currentView === 'sessions-list'">
                    <div v-if="isOpeningSession" class="mb-4 flex items-center space-x-3 rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                        <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4"></circle>
                            <path class="opacity-75" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M4 12a8 8 0 018-8"></path>
                        </svg>
                        <span>Opening session details...</span>
                    </div>
                    <!-- Sessions Header -->
                    <div class="rounded-2xl border border-white/20 bg-white/10 backdrop-blur-xl p-6 mb-6 shadow-2xl shadow-indigo-950/40">
                    <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between mb-6">
                        <div class="flex items-center space-x-4">
                            <h2 class="text-xl font-semibold text-white">Dashboard Sessions</h2>
                            
                            <!-- Filter Button -->
                            <button 
                                @click="filterSessions"
                                class="flex items-center space-x-2 px-3 py-2 text-sm text-slate-100 border border-white/30 rounded-xl bg-white/10 hover:bg-white/20 transition-all"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.414A1 1 0 013 6.707V4z"></path>
                                </svg>
                                <span>Filter Sessions</span>
                            </button>
                        </div>

                        <!-- Search, Delete, and New Session -->
                        <div class="flex flex-wrap items-center gap-3">
                            <!-- Search -->
                            <div class="relative">
                                <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                                </svg>
                                <input
                                    v-model="searchQuery"
                                    @input="searchSessions"
                                    type="text"
                                    placeholder="Search by Session Reference"
                                    class="pl-10 pr-4 py-2 w-64 border border-white/30 bg-white/10 text-white placeholder:text-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300 text-sm"
                                />
                            </div>

                            <!-- Page Size Selector -->
                            <div class="flex items-center space-x-2 text-sm text-slate-200">
                                <span>Rows per page:</span>
                                <select
                                    v-model.number="itemsPerPage"
                                    class="border border-white/30 rounded-xl px-2 py-1 bg-white/10 text-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
                                >
                                    <option v-for="option in pageSizeOptions" :key="option" :value="option">
                                        {{ option }}
                                    </option>
                                </select>
                            </div>

                            <!-- Bulk Delete Button -->
                            <button 
                                @click="bulkDeleteSessions"
                                :disabled="selectedSessions.length === 0"
                                :class="[
                                    'flex items-center space-x-2 px-4 py-2 text-sm font-medium rounded-md transition-colors',
                                    selectedSessions.length === 0 
                                        ? 'text-slate-400 bg-white/10 cursor-not-allowed' 
                                        : 'text-rose-100 bg-rose-500/20 border border-rose-300/30 hover:bg-rose-500/30'
                                ]"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                </svg>
                                <span>Delete Selected ({{ selectedSessions.length }})</span>
                            </button>

                            <!-- New Session Button -->
                            <button 
                                @click="startNewSession"
                                class="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-violet-500 text-white text-sm font-semibold rounded-xl shadow-lg hover:scale-[1.02] transition-all"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                                </svg>
                                <span>New Session</span>
                            </button>
                        </div>
                    </div>

                    <!-- Sessions Table -->
                    <div class="bg-white/10 border border-white/20 rounded-2xl overflow-hidden backdrop-blur-xl">
                        <!-- Table Header -->
                        <div class="border-b border-white/20 bg-slate-900/50 px-6 py-3">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center space-x-4 flex-1">
                                    <!-- Select All Checkbox -->
                                    <div class="flex items-center w-16">
                                        <input
                                            type="checkbox"
                                            :checked="visibleSelectionState.allSelected"
                                            :indeterminate="visibleSelectionState.partiallySelected"
                                            @change="selectAllSessions"
                                            class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                                        />
                                        <label class="ml-2 text-sm font-medium text-gray-700">Select</label>
                                    </div>

                                    <!-- Column Headers -->
                                    <div class="flex-1 grid grid-cols-4 gap-4 text-sm font-medium text-slate-200">
                                        <div class="flex items-center cursor-pointer" @click="sortBy('reference')">
                                            Session Reference
                                            <svg class="ml-1 w-3 h-3" :class="{
                                                'rotate-180': sortField === 'reference' && sortDirection === 'desc'
                                            }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 15l4 4 4-4m0-6l-4-4-4 4"></path>
                                            </svg>
                                        </div>
                                        <div class="flex items-center cursor-pointer" @click="sortBy('date')">
                                             Date
                                            <svg class="ml-1 w-3 h-3" :class="{
                                                'rotate-180': sortField === 'date' && sortDirection === 'desc'
                                            }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 15l4 4 4-4m0-6l-4-4-4 4"></path>
                                            </svg>
                                        </div>
                                        <div> Topic</div>
                                        <div> Form Status</div>
                                    </div>
                                    <div class="text-sm font-medium text-slate-200">Actions</div>
                                </div>
                            </div>
                        </div>

                        <!-- Session Rows -->
                        <div v-if="filteredSessions.length > 0">
                            <div 
                                v-for="session in paginatedSessions" 
                                :key="session.id"
                                class="px-6 py-4 hover:bg-white/10 cursor-pointer border-b border-white/10 last:border-b-0" 
                                @click="showSessionDetails(session.id)"
                            >
                                <div class="flex items-center justify-between">
                                    <div class="flex items-center space-x-4 flex-1">
                                        <div class="w-16">
                                            <input 
                                                type="checkbox" 
                                                :checked="selectedSessions.includes(session.id)"
                                                @click.stop="toggleSessionSelection(session.id)"
                                                class="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500" 
                                            />
                                        </div>
                                        <div class="flex-1 grid grid-cols-4 gap-4 text-sm">
                                            <div class="text-white hover:text-indigo-200 font-medium">{{ session.reference }}</div>
                                            <div class="text-slate-200">{{ session.date }}</div>
                                            <div class="text-slate-200">
                                                <span class="border border-white/30 bg-white/10 rounded-lg px-2 py-1 inline-block">{{ session.topic }}</span>
                                            </div>
                                            <div>
                                                <StatusBadge :status="session.status" />
                                                <div
                                                    v-if="isProcessingStatus(session.status)"
                                                    class="mt-1 text-xs text-slate-300"
                                                >
                                                    <span v-if="session.processing_progress >= 0">{{ Math.round(session.processing_progress || 0) }}%</span>
                                                    <span v-if="session.processing_stage"> · {{ session.processing_stage }}</span>
                                                    <span v-if="session.processing_message"> · {{ session.processing_message }}</span>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="relative flex items-center">
                                            <button 
                                                class="text-gray-400 hover:text-gray-600 p-1" 
                                                @click.stop="toggleDropdown(session.id)"
                                            >
                                                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                                    <path d="M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
                                                </svg>
                                            </button>
                                            <div 
                                                v-if="showDropdownId === session.id" 
                                                class="absolute right-0 top-8 w-48 bg-slate-900 border border-white/20 rounded-xl shadow-lg z-10"
                                                @click.stop
                                            >
                                                <div class="py-1">
                                                    <button
                                                        v-if="session.status === 'disconnected'"
                                                        class="w-full text-left px-4 py-2 text-sm text-green-700 hover:bg-green-50 font-medium"
                                                        @click="resumeSession(session)"
                                                    >
                                                        Resume Session
                                                    </button>
                                                    <button
                                                        class="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-white/10"
                                                        @click="openCRMForm(session)"
                                                    >
                                                        Open CRM Form
                                                    </button>
                                                    <button 
                                                        class="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-white/10"
                                                        @click="openSession(session)"
                                                    >
                                                        Open Session
                                                    </button>
                                                    <button 
                                                        class="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-white/10"
                                                        @click="viewPDF(session)"
                                                    >
                                                        View PDF
                                                    </button>
                                                    <button 
                                                        class="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                                                        @click="deleteSession(session)"
                                                    >
                                                        Delete Session
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Empty State -->
                        <div v-if="filteredSessions.length === 0 && !isLoading" class="text-center py-16">
                            <div class="text-slate-300 mb-4">
                                <svg class="w-12 h-12 mx-auto mb-4 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                </svg>
                            </div>
                            <h3 class="text-lg font-medium text-white mb-2">
                                Looks like you have no saved sessions.
                            </h3>
                            <p class="text-slate-200 mb-6">
                                Start a session by clicking the "New Session" button in the top right corner of the page!
                            </p>
                        </div>

                        <!-- Loading State -->
                        <div v-if="isLoading" class="text-center py-16">
                            <div class="text-slate-200">Loading sessions...</div>
                        </div>
                    </div>
                    </div>

                    <!-- Pagination -->
                    <div v-if="filteredSessions.length > 0" class="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div class="text-sm text-gray-600">
                            Showing {{ pageDisplayRange.start }} - {{ pageDisplayRange.end }} of {{ filteredSessions.length }} sessions
                        </div>
                        <div class="flex items-center space-x-2">
                            <button
                                @click="goToFirstPage"
                                :disabled="currentPage === 1"
                                :class="[
                                    'p-2 rounded border border-gray-200 transition-colors',
                                    currentPage === 1 ? 'text-gray-300 cursor-not-allowed' : 'text-gray-500 hover:text-gray-700'
                                ]"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7"></path>
                                </svg>
                            </button>
                            <button
                                @click="prevPage"
                                :disabled="currentPage === 1"
                                :class="[
                                    'p-2 rounded border border-gray-200 transition-colors',
                                    currentPage === 1 ? 'text-gray-300 cursor-not-allowed' : 'text-gray-500 hover:text-gray-700'
                                ]"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
                                </svg>
                            </button>
                            
                            <span class="px-3 py-2 text-sm bg-blue-600 text-white rounded">
                                Page {{ currentPage }} of {{ totalPages }}
                            </span>
                            
                            <button
                                @click="nextPage"
                                :disabled="currentPage === totalPages"
                                :class="[
                                    'p-2 rounded border border-gray-200 transition-colors',
                                    currentPage === totalPages ? 'text-gray-300 cursor-not-allowed' : 'text-gray-500 hover:text-gray-700'
                                ]"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                                </svg>
                            </button>
                            <button
                                @click="goToLastPage"
                                :disabled="currentPage === totalPages"
                                :class="[
                                    'p-2 rounded border border-gray-200 transition-colors',
                                    currentPage === totalPages ? 'text-gray-300 cursor-not-allowed' : 'text-gray-500 hover:text-gray-700'
                                ]"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"></path>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Session Details View -->
                <div v-else-if="currentView === 'session-details'">
                    <!-- Session Header -->
                    <div class="flex items-center justify-between mb-6">
                        <div class="flex items-center space-x-6">
                            <button 
                                @click="showSessionsList"
                                class="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
                                </svg>
                                <span>Back to Sessions</span>
                            </button>
                            <div class="flex items-center space-x-4">
                                <span class="text-base font-medium text-gray-900">Session:</span>
                                <div v-if="isEditingSessionName" class="flex items-center space-x-2">
                                    <input
                                        v-model="editedSessionName"
                                        @keyup.enter.prevent="saveSessionNameEdit"
                                        :disabled="isSavingSessionName"
                                        type="text"
                                        placeholder="Enter session name"
                                        class="px-3 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                                    />
                                    <button 
                                        @click.stop="saveSessionNameEdit"
                                        :disabled="isSavingSessionName"
                                        class="flex items-center space-x-1 px-3 py-1 rounded-md text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <svg v-if="isSavingSessionName" class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4"></circle>
                                            <path class="opacity-75" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M4 12a8 8 0 018-8"></path>
                                        </svg>
                                        <span>{{ isSavingSessionName ? 'Saving' : 'Save' }}</span>
                                    </button>
                                    <button 
                                        @click.stop="cancelSessionNameEdit"
                                        :disabled="isSavingSessionName"
                                        class="px-3 py-1 rounded-md text-xs font-medium text-gray-600 border border-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        Cancel
                                    </button>
                                </div>
                                <div v-else class="flex items-center space-x-2">
                                    <span class="text-base font-semibold text-gray-900">{{ selectedSessionRef || '—' }}</span>
                                    <button 
                                        v-if="canEditSessionName"
                                        @click.stop="startEditingSessionName"
                                        class="p-1 rounded-md border border-gray-200 text-gray-500 hover:text-gray-700 hover:border-gray-300 transition-colors"
                                        title="Rename session"
                                    >
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                                        </svg>
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                    <div class="flex items-center space-x-3">
                        <button 
                            @click="launchExperiment"
                                class="flex items-center space-x-2 px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                                </svg>
                                <span>Start Experiment</span>
                            </button>
                            <button
                                @click="openCRMFormPage"
                                class="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                                </svg>
                                <span>Fill CRM Form</span>
                            </button>
                            <button
                                v-if="selectedSession && selectedSession.status === 'disconnected'"
                                @click="resumeSession(selectedSession)"
                                class="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                                </svg>
                                <span>Resume Session</span>
                            </button>
                            <button
                                @click="startNewSession"
                                class="flex items-center space-x-2 px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l11-7z"/>
                                </svg>
                                <span>Start Another Session</span>
                            </button>
                        </div>
                    </div>

                    <div 
                        v-if="selectedSession && isProcessingStatus(selectedSession.status)"
                        class="mb-6 rounded-md border border-yellow-200 bg-yellow-50 px-4 py-4 text-sm text-yellow-800 space-y-3"
                    >
                        <div class="flex items-start space-x-3">
                            <svg class="h-5 w-5 animate-spin text-yellow-600 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4"></circle>
                                <path class="opacity-75" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M4 12a8 8 0 018-8"></path>
                            </svg>
                            <div>
                                <p class="text-sm font-semibold">Session is currently processing</p>
                                <p class="text-xs mt-1 text-yellow-800/90">
                                    <span v-if="selectedSession?.processing_progress >= 0">{{ Math.round(selectedSession.processing_progress) }}% · </span>
                                    <span v-if="selectedSession?.processing_stage">{{ selectedSession.processing_stage }}</span>
                                    <span v-if="selectedSession?.processing_message"> · {{ selectedSession.processing_message }}</span>
                                </p>
                            </div>
                        </div>
                        <div class="h-2 w-full bg-yellow-100 rounded overflow-hidden">
                            <div
                                v-if="selectedSession?.processing_progress >= 0"
                                class="h-full bg-yellow-500 transition-all duration-300"
                                :style="{ width: Math.max(0, Math.min(100, selectedSession?.processing_progress || 0)) + '%' }"
                            ></div>
                            <div
                                v-else
                                class="h-full bg-yellow-500 animate-pulse"
                                style="width: 100%"
                            ></div>
                        </div>
                        <div class="flex flex-wrap gap-2">
                            <button
                                @click="loadSessions"
                                class="inline-flex items-center space-x-2 px-3 py-1.5 text-xs font-medium rounded-md border border-yellow-300 text-yellow-800 hover:bg-yellow-100 transition-colors"
                            >
                                <svg class="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M3 4a1 1 0 011-1h4a1 1 0 010 2H6.414l1.293 1.293a1 1 0 01-1.414 1.414L4 6.414V9a1 1 0 11-2 0V5a1 1 0 011-1zm14 12a1 1 0 01-1 1h-4a1 1 0 110-2h1.586l-1.293-1.293a1 1 0 111.414-1.414L16 13.586V11a1 1 0 112 0v4z" clip-rule="evenodd" />
                                </svg>
                                <span>Refresh Status</span>
                            </button>
                        </div>
                    </div>

                    <!-- Session Details -->
                    <div class="space-y-4 mb-6">
                        <div class="flex items-center space-x-4">
                            <span class="text-base font-medium text-gray-900">Related Sessions:</span>
                            <div class="flex space-x-3">
                                <span class="text-gray-500 text-sm italic">Will show related sessions from database</span>
                            </div>
                        </div>
                        <div class="flex items-center space-x-4">
                            <span class="text-base font-medium text-gray-900">Additional Translation Languages:</span>
                        </div>
                    </div>

                <!-- Two Column Layout -->
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    <!-- Left Column: Topics Discussed (2/3 width) -->
                    <div class="lg:col-span-2 space-y-6">
                        <div class="flex items-center justify-between">
                            <h3 class="text-base font-medium text-gray-900">Topics discussed during the session:</h3>
                            <button 
                                @click="viewTranscript"
                                :class="[
                                    'flex items-center space-x-2 px-3 py-2 text-sm font-medium rounded-md transition-colors',
                                    showTranscript ? 'bg-gray-600 text-white hover:bg-gray-700' : 'bg-black text-white hover:bg-gray-600'
                                ]"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                </svg>
                                <span>{{ showTranscript ? 'Hide Transcript' : 'View Transcript' }}</span>
                            </button>
                        </div>
                        
                        <!-- Loading State -->
                        <div v-if="loadingTopics" class="text-center py-8">
                            <div class="text-gray-500">Loading session summary...</div>
                        </div>

                        <!-- Topic Cards -->
                        <div v-else class="space-y-4">
                            <div class="bg-white border border-gray-200 rounded-lg p-4">
                                <div class="flex items-center justify-between mb-2">
                                    <h4 class="text-sm font-medium text-gray-900">Session Overview</h4>
                                    <div v-if="!isEditingOverview" class="flex space-x-2">
                                        <button
                                            @click="startEditingOverview"
                                            class="flex items-center space-x-1 px-2 py-1 text-xs text-blue-600 hover:text-blue-800 bg-blue-50 rounded"
                                        >
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                            </svg>
                                            <span>Edit</span>
                                        </button>
                                    </div>
                                    <div v-else class="flex space-x-2">
                                        <button
                                            @click="saveOverview"
                                            :disabled="savingOverview"
                                            class="flex items-center space-x-1 px-2 py-1 text-xs text-green-600 hover:text-green-800 bg-green-50 rounded disabled:opacity-50"
                                        >
                                            <svg v-if="savingOverview" class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                            </svg>
                                            <svg v-else class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                            </svg>
                                            <span>{{ savingOverview ? 'Saving...' : 'Save' }}</span>
                                        </button>
                                        <button
                                            @click="cancelEditingOverview"
                                            :disabled="savingOverview"
                                            class="flex items-center space-x-1 px-2 py-1 text-xs text-gray-600 hover:text-gray-800 bg-gray-50 rounded disabled:opacity-50"
                                        >
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                            </svg>
                                            <span>Cancel</span>
                                        </button>
                                    </div>
                                </div>
                                <div v-if="isEditingOverview">
                                    <textarea
                                        v-model="editingOverviewText"
                                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm resize-y"
                                        :rows="Math.max(4, Math.ceil((editingOverviewText?.length || 0) / 80))"
                                        :disabled="savingOverview"
                                    ></textarea>
                                </div>
                                <p v-else class="text-sm text-gray-700 whitespace-pre-wrap">
                                    {{ overviewText || 'Summary is not available yet.' }}
                                </p>
                            </div>

                            <TopicCard
                                v-for="topic in topics"
                                :key="topic.id"
                                :topic="topic"
                                :is-editing="editingTopic === topic.id"
                                :editing-draft="editingTopicDraft"
                                @toggle="toggleTopic"
                                @delete="deleteTopic"
                                @start-edit="startEditingTopic"
                                @save-edit="saveTopicEdit"
                                @cancel-edit="cancelTopicEdit"
                                @update:editingDraft="editingTopicDraft = $event"
                            />

                            <!-- Add Topic Button -->
                            <button 
                                @click="addTopic"
                                class="w-full flex items-center justify-center space-x-2 py-4 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-gray-400 hover:text-gray-600 transition-colors"
                            >
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                                </svg>
                                <span class="font-medium">Add Topic</span>
                            </button>
                        </div>

                        <!-- Inline Transcript View -->
                        <TranscriptViewer
                            v-if="showTranscript"
                            :session-ref="selectedSessionRef"
                            :transcript-data="transcriptData"
                            :loading="loadingTranscript"
                            :editing="editingTranscript"
                            :edited-entries="editedTranscriptEntries"
                            @close="closeTranscript"
                            @start-edit="startEditingTranscript"
                            @save="saveTranscriptChanges"
                            @cancel-edit="cancelTranscriptEdit"
                            @update:editedEntries="editedTranscriptEntries = $event"
                        />
                    </div>

                    <!-- Right Column: Notes and Export (1/3 width) -->
                    <div class="space-y-6">
                        <!-- Language Section -->
                        <div class="bg-white border border-gray-200 rounded-lg p-4">
                            <h4 class="text-sm font-medium text-gray-900 mb-3">Translate Summary</h4>
                            <div class="flex flex-wrap gap-2 mb-3">
                                <button
                                    v-for="lang in availableLanguages"
                                    :key="lang.code"
                                    @click="selectedLanguage = lang.name"
                                    :class="[
                                        'px-3 py-1.5 text-xs font-medium rounded-full border transition-colors cursor-pointer',
                                        selectedLanguage === lang.name
                                            ? 'bg-black text-white border-black'
                                            : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-100 hover:border-gray-400'
                                    ]"
                                >
                                    {{ lang.name }}
                                </button>
                            </div>
                            <button
                                @click="translateCurrentSummary"
                                :disabled="loadingTopics || !selectedLanguage.trim()"
                                class="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <svg v-if="loadingTopics" class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4"></circle>
                                    <path class="opacity-75" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M4 12a8 8 0 018-8"></path>
                                </svg>
                                <span>{{ loadingTopics ? 'Translating...' : 'Translate' }}</span>
                            </button>
                        </div>

                        <!-- Export Section -->
                        <div class="bg-white border border-gray-200 rounded-lg p-4">
                            <h4 class="text-sm font-medium text-gray-900 mb-4">Export Output</h4>
                            <!-- <div class="space-y-3">
                                <button 
                                    @click="previewPDF"
                                    class="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-600 transition-colors"
                                >
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                    </svg>
                                    <span>Generate PDF</span>
                                </button>
                                <button  -->
                            <div class="space-y-3">
                                <button
                                    @click="downloadPDF"
                                    :disabled="isGeneratingPdf || loadingTopics"
                                    class="w-full flex items-center justify-center space-x-2 px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <svg v-if="isGeneratingPdf" class="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4"></circle>
                                        <path class="opacity-75" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M4 12a8 8 0 018-8"></path>
                                    </svg>
                                    <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                    </svg>
                                    <span>{{ isGeneratingPdf ? 'Generating PDF...' : 'Download PDF' }}</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                </div>
            </main>

            <!-- CRM Popup Modal -->
            <BaseModal :show="showCRMPopup" @close="closeCRMPopup">
                    <div class="text-center">
                        <h3 class="text-lg font-medium text-gray-900 mb-4">
                            Submit the CRM form?
                        </h3>
                        <p class="text-sm text-gray-600 mb-6">
                            You haven't submitted your CRM form yet.<br>
                            What would you like to do?
                        </p>
                        
                        <div class="flex space-x-3">
                            <button 
                                @click="deleteSessionFromPopup"
                                class="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                </svg>
                                <span>Delete Session</span>
                            </button>
                            
                            <button 
                                @click="saveAsDraft"
                                class="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3-3m0 0l-3 3m3-3v12"></path>
                                </svg>
                                <span>Save as a draft</span>
                            </button>
                            
                            <button 
                                @click="continueEditing"
                                class="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-600 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                </svg>
                                <span>Continue Editing</span>
                            </button>
                        </div>
                    </div>
            </BaseModal>

            <!-- Finish Session Popup Modal -->
            <BaseModal :show="showFinishSessionPopup" max-width="max-w-lg" @close="closeFinishSessionPopup">
                    <div class="text-center">
                        <h3 class="text-lg font-medium text-gray-900 mb-4">
                            What would you like to do with your session?
                        </h3>
                        <p class="text-sm text-gray-600 mb-6">
                            You're about to finish this session.<br>
                            Choose what you'd like to do with your session notes and summary.
                        </p>
                        
                        <div class="flex space-x-3">
                            <button 
                                @click="deleteSessionFromFinishPopup"
                                class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                </svg>
                                <span>Delete Session</span>
                            </button>
                            
                            <button 
                                @click="saveSession"
                                class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3-3m0 0l-3 3m3-3v12"></path>
                                </svg>
                                <span>Save Session</span>
                            </button>
                            
                            <button 
                                @click="saveAndEditSummary"
                                class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-600 transition-colors"
                            >
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                                </svg>
                                <span>Save & Edit Summary</span>
                            </button>
                        </div>
                    </div>
            </BaseModal>

            <!-- Add Topic Popup Modal -->
            <BaseModal :show="showAddTopicPopup" @close="closeAddTopicPopup">
                    <div class="text-center">
                        <h3 class="text-lg font-medium text-gray-900 mb-4">
                            Add New Topic
                        </h3>
                        <p class="text-sm text-gray-600 mb-6">
                            Enter a topic reference and our AI will analyze the session transcript to find related content and generate a summary.
                        </p>
                        
                        <div class="mb-6">
                            <label for="topicReference" class="block text-sm font-medium text-gray-700 text-left mb-2">
                                Topic Reference
                            </label>
                            <input
                                id="topicReference"
                                v-model="newTopicReference"
                                type="text"
                                placeholder="e.g., Employment, Language Learning, Healthcare..."
                                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
                                :disabled="generatingTopic"
                                @keydown.enter="generateNewTopic"
                            />
                        </div>
                        
                        <div class="flex space-x-3">
                            <button 
                                @click="closeAddTopicPopup"
                                :disabled="generatingTopic"
                                class="flex-1 px-4 py-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50"
                            >
                                Cancel
                            </button>
                            
                            <button 
                                @click="generateNewTopic"
                                :disabled="generatingTopic || !newTopicReference.trim()"
                                class="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
                            >
                                <svg v-if="generatingTopic" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                                </svg>
                                <span>{{ generatingTopic ? 'Generating...' : 'Generate Topic' }}</span>
                            </button>
                        </div>
                    </div>
            </BaseModal>

            <!-- Confirm Modal -->
            <BaseModal :show="showConfirmModal" max-width="max-w-sm" @close="cancelConfirm">
                <div>
                    <h3 class="text-lg font-semibold text-gray-900 mb-2">Confirm Delete</h3>
                    <p class="text-sm text-gray-600 mb-6">{{ confirmModalMessage }}</p>
                    <div class="flex space-x-3">
                        <button @click="cancelConfirm" class="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors">
                            Cancel
                        </button>
                        <button @click="confirmAction" class="flex-1 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors">
                            Delete
                        </button>
                    </div>
                </div>
            </BaseModal>

            <!-- Notification Modal -->
            <NotificationModal
                :show="showNotificationModal"
                :title="notificationTitle"
                :message="notificationMessage"
                :type="notificationType"
                @close="closeNotificationModal"
            />

            <!-- PDF Preview Modal -->
            <div 
                v-if="showPdfPreviewModal" 
                class="fixed inset-0 backdrop-blur-sm bg-white/30 flex items-center justify-center z-50"
                @click="closePdfPreviewModal"
            >
                <div 
                    class="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 h-5/6"
                    @click.stop
                >
                    <div class="flex items-center justify-between p-4 border-b border-gray-200">
                        <h3 class="text-lg font-medium text-gray-900">
                            PDF Preview
                        </h3>
                        <button 
                            @click="closePdfPreviewModal"
                            class="text-gray-400 hover:text-gray-600 transition-colors"
                        >
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>
                    <div class="p-4 h-full">
                        <iframe 
                            v-if="pdfPreviewUrl"
                            :src="pdfPreviewUrl"
                            class="w-full h-full border-0"
                            title="PDF Preview"
                        ></iframe>
                    </div>
                </div>
            </div>
        </div>
    `
};
