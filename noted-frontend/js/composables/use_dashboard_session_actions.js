import { ref, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { sessionService } from '../services/session_service.js';

export function useDashboardSessionActions({
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
}) {
    const router = useRouter();
    const route = useRoute();
    const isEditingSessionName = ref(false);
    const editedSessionName = ref('');
    const isSavingSessionName = ref(false);
    const showCRMPopup = ref(false);
    const showFinishSessionPopup = ref(false);
    const showConfirmModal = ref(false);
    const confirmModalMessage = ref('');
    const confirmModalAction = ref(null);

    const canEditSessionName = computed(() => {
        if (!selectedSession.value) {
            return false;
        }

        const statusValue = selectedSession.value.status
            ? selectedSession.value.status.toString().toLowerCase()
            : '';
        return statusValue === 'completed';
    });

    const syncEditedSessionName = () => {
        editedSessionName.value = selectedSession.value?.reference || '';
        isEditingSessionName.value = false;
    };

    const openCRMForm = (session) => {
        selectedSession.value = session;
        showCRMPopup.value = true;
        closeDropdown();
    };

    const closeCRMPopup = () => {
        showCRMPopup.value = false;
        selectedSession.value = null;
    };

    const withConfirmation = (message, action) => {
        confirmModalMessage.value = message;
        confirmModalAction.value = action;
        showConfirmModal.value = true;
    };

    const confirmAction = () => {
        showConfirmModal.value = false;
        if (confirmModalAction.value) {
            confirmModalAction.value();
        }
    };

    const cancelConfirm = () => {
        showConfirmModal.value = false;
        confirmModalAction.value = null;
    };

    const deleteSession = (session) => {
        withConfirmation(
            `Are you sure you want to delete session ${session.reference}? This action cannot be undone.`,
            async () => {
                try {
                    const success = await sessionService.deleteSession(session.id);
                    if (!success) {
                        showNotification('Error', 'Failed to delete session.', 'error');
                        return;
                    }

                    await loadSessions();
                    showNotification('Success', 'Session deleted successfully.', 'success');
                } catch (error) {
                    console.error('Error deleting session:', error);
                    showNotification('Error', 'Failed to delete session.', 'error');
                }
            }
        );

        closeDropdown();
    };

    const deleteSessionFromPopup = async () => {
        if (selectedSession.value) {
            await deleteSession(selectedSession.value);
        }
        closeCRMPopup();
    };

    const saveAsDraft = () => {
        console.log('Saving as draft for session:', selectedSession.value?.reference);
        closeCRMPopup();
    };

    const continueEditing = () => {
        console.log('Continue editing for session:', selectedSession.value?.reference);
        closeCRMPopup();
    };

    const showFinishSessionDialog = () => {
        showFinishSessionPopup.value = true;
    };

    const closeFinishSessionPopup = () => {
        showFinishSessionPopup.value = false;
    };

    const deleteSessionFromFinishPopup = async () => {
        if (selectedSession.value) {
            await deleteSession(selectedSession.value);
        }
        closeFinishSessionPopup();
    };

    const saveSession = () => {
        console.log('Saving session:', selectedSessionRef.value);
        closeFinishSessionPopup();
    };

    const saveAndEditSummary = () => {
        console.log('Save and edit summary for session:', selectedSessionRef.value);
        closeFinishSessionPopup();
    };

    const showSessionDetails = async (sessionIdentifier, updateRoute = true) => {
        const session = setSelectedSession(sessionIdentifier);
        if (!session) {
            return;
        }

        currentView.value = 'session-details';
        if (updateRoute) {
            await router.push({
                name: 'session-detail',
                params: { sessionId: session.id || session.reference },
            });
        }

        await loadSessionSummary(session);
    };

    const showSessionsList = async () => {
        finalizeTopicEdit(true, true);
        currentView.value = 'sessions-list';
        selectedSession.value = null;
        pendingSessionToOpen.value = null;
        isOpeningSession.value = false;

        if (route.name !== 'dashboard') {
            await router.push({ name: 'dashboard' });
        }
    };

    const openSession = (session) => {
        void showSessionDetails(session.id);
        closeDropdown();
    };

    const resumeSession = async (session) => {
        closeDropdown();
        if (session.websocket_session_id) {
            sessionService.setWebSocketSessionId(session.websocket_session_id);
        }

        await router.push({
            name: 'recording',
            params: { sessionId: session.reference },
        });
    };

    const viewPDF = (session) => {
        console.log('Viewing PDF for session:', session.reference);
        closeDropdown();
    };

    const startNewSession = async () => {
        await router.push({ name: 'new-session' });
    };

    const launchExperiment = async () => {
        if (!selectedSession.value) {
            showNotification('Warning', 'Select a session first.', 'info');
            return;
        }

        await router.push({
            name: 'experiment',
            params: {
                sessionId: selectedSessionDbId.value || selectedSessionRef.value,
            },
        });
    };

    const openCRMFormPage = async () => {
        if (!selectedSession.value) {
            return;
        }

        const sessionId = selectedSessionDbId.value || selectedSessionRef.value;
        await router.push({ name: 'crm-form', params: { sessionId } });
    };

    const bulkDeleteSessions = async () => {
        if (selectedSessions.value.length === 0) {
            showNotification('Warning', 'Please select sessions to delete.', 'info');
            return;
        }

        withConfirmation(
            `Are you sure you want to delete ${selectedSessions.value.length} selected session(s)? This action cannot be undone.`,
            async () => {
                isLoading.value = true;
                try {
                    const sessionReferences = selectedSessions.value
                        .map(sessionId => sessionsById.value.get(sessionId)?.reference || null)
                        .filter(Boolean);

                    const result = await sessionService.bulkDeleteSessions(sessionReferences);
                    showNotification('Success', `Successfully deleted ${result.deleted_count} sessions.`, 'success');

                    selectedSessions.value = [];
                    await loadSessions();
                } catch (error) {
                    console.error('Failed to delete sessions:', error);
                    showNotification('Error', 'Failed to delete sessions. Please try again.', 'error');
                } finally {
                    isLoading.value = false;
                }
            }
        );
    };

    const startEditingSessionName = () => {
        if (!canEditSessionName.value) {
            return;
        }

        editedSessionName.value = selectedSessionRef.value || '';
        isEditingSessionName.value = true;
    };

    const cancelSessionNameEdit = () => {
        editedSessionName.value = selectedSessionRef.value || '';
        isEditingSessionName.value = false;
    };

    const saveSessionNameEdit = async () => {
        if (!selectedSession.value) {
            showNotification('Warning', 'No session selected', 'info');
            return;
        }

        const trimmedName = editedSessionName.value.trim();
        if (!trimmedName) {
            showNotification('Warning', 'Session name cannot be empty', 'info');
            return;
        }

        if (trimmedName === selectedSessionRef.value) {
            isEditingSessionName.value = false;
            return;
        }

        isSavingSessionName.value = true;
        try {
            const identifier = selectedSessionDbId.value || selectedSessionRef.value;
            const updatedSession = await sessionService.renameSession(identifier, trimmedName);
            applySessionUpdate(updatedSession);
            showNotification('Success', 'Session name updated successfully.', 'success');
            editedSessionName.value = trimmedName;
            isEditingSessionName.value = false;
        } catch (error) {
            console.error('Failed to rename session:', error);
            showNotification('Error', error.message || 'Failed to rename session.', 'error');
        } finally {
            isSavingSessionName.value = false;
        }
    };

    const logout = () => {
        authService.logout();
        window.location.reload();
    };

    return {
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
    };
}
