import { ref, computed } from 'vue';
import { sessionService } from '../services/session_service.js';
import { useSessionTopics } from './use_session_topics.js';
import { useSessionTranscript } from './use_session_transcript.js';

export function useSessionDetail({
    selectedSession,
    selectedSessionDbId,
    selectedSessionRef,
    showNotification,
}) {
    const sessionSummary = ref(null);
    const originalTopics = ref([]);
    const originalSessionSummary = ref(null);
    const translatedLanguage = ref('');
    const loadingTopics = ref(false);

    const selectedLanguage = ref('');
    const availableLanguages = [
        { code: 'fi', name: 'Finnish' },
        { code: 'sv', name: 'Swedish' },
        { code: 'ar', name: 'Arabic' },
        { code: 'ru', name: 'Russian' },
        { code: 'es', name: 'Spanish' },
        { code: 'fr', name: 'French' },
        { code: 'de', name: 'German' },
        { code: 'zh', name: 'Chinese' },
        { code: 'vi', name: 'Vietnamese' },
        { code: 'hi', name: 'Hindi' },
        { code: 'uk', name: 'Ukrainian' },
        { code: 'ja', name: 'Japanese' },
        { code: 'ko', name: 'Korean' },
        { code: 'pt', name: 'Portuguese' },
        { code: 'it', name: 'Italian' },
        { code: 'pl', name: 'Polish' },
        { code: 'tr', name: 'Turkish' },
        { code: 'nl', name: 'Dutch' },
        { code: 'cs', name: 'Czech' },
        { code: 'en', name: 'English' },
    ];

    const isEditingOverview = ref(false);
    const editingOverviewText = ref('');
    const savingOverview = ref(false);

    const advisorNotes = ref('');
    const isEditingNotes = ref(false);
    const notesBeingEdited = ref('');
    const savingNotes = ref(false);

    const cloneValue = (value) => {
        if (value === undefined || value === null) {
            return value;
        }
        return structuredClone(value);
    };

    const overviewText = computed(() => {
        const summary = sessionSummary.value || {};
        return (summary.overview || '').trim();
    });

    const startEditingNotes = () => {
        notesBeingEdited.value = advisorNotes.value;
        isEditingNotes.value = true;
    };

    const cancelEditingNotes = () => {
        notesBeingEdited.value = '';
        isEditingNotes.value = false;
    };

    const saveAdvisorNotes = async () => {
        if (!selectedSession.value) {
            showNotification('Warning', 'No session selected', 'info');
            return;
        }

        savingNotes.value = true;
        try {
            const result = await sessionService.updateSessionNotes(
                selectedSessionDbId.value,
                notesBeingEdited.value
            );
            advisorNotes.value = result.notes ?? notesBeingEdited.value;
            cancelEditingNotes();
        } catch (error) {
            console.error('Failed to save advisor notes:', error);
            showNotification('Error', 'Failed to save notes. Please try again.', 'error');
        } finally {
            savingNotes.value = false;
        }
    };

    const startEditingOverview = () => {
        editingOverviewText.value = overviewText.value;
        isEditingOverview.value = true;
    };

    const cancelEditingOverview = () => {
        editingOverviewText.value = '';
        isEditingOverview.value = false;
    };

    const saveOverview = async () => {
        if (!selectedSession.value) {
            return;
        }

        savingOverview.value = true;
        try {
            const result = await sessionService.updateSessionOverview(
                selectedSessionDbId.value,
                editingOverviewText.value
            );
            const savedOverview = result.overview ?? editingOverviewText.value;
            const summary = sessionSummary.value || {};
            summary.overview = savedOverview;
            sessionSummary.value = { ...summary };
            isEditingOverview.value = false;
        } catch (error) {
            console.error('Failed to save overview:', error);
            showNotification('Error', 'Failed to save overview. Please try again.', 'error');
        } finally {
            savingOverview.value = false;
        }
    };

    const loadSessionSummary = async (sessionLike = null) => {
        const session = (sessionLike && typeof sessionLike === 'object')
            ? sessionLike
            : selectedSession.value;
        if (!session) {
            console.error('Cannot load summary: session not resolved', sessionLike);
            return;
        }

        loadingTopics.value = true;
        topics.value = [];
        sessionSummary.value = null;
        originalTopics.value = [];
        originalSessionSummary.value = null;
        translatedLanguage.value = '';
        advisorNotes.value = '';

        try {
            const summary = await sessionService.getSessionSummary(session.id);
            sessionSummary.value = summary;
            advisorNotes.value = await sessionService.getSessionNotes(session.id);
            setTopicsFromSummary(summary);
            originalSessionSummary.value = cloneValue(summary);
            originalTopics.value = cloneValue(topics.value);
        } catch (error) {
            console.error('Failed to load session summary:', error);
            sessionSummary.value = {
                overview: 'Unable to load session summary. Please try again.',
                action_items: [],
                topics_discussed: [],
            };
            setTopicsFromSummary(sessionSummary.value);
            originalSessionSummary.value = cloneValue(sessionSummary.value);
            originalTopics.value = cloneValue(topics.value);
        } finally {
            loadingTopics.value = false;
        }
    };
    const {
        topics,
        editingTopic,
        editingTopicDraft,
        showAddTopicPopup,
        newTopicReference,
        generatingTopic,
        setTopicsFromSummary,
        finalizeTopicEdit,
        toggleTopic,
        deleteTopic,
        addTopic,
        showAddTopicDialog,
        closeAddTopicPopup,
        generateNewTopic,
        startEditingTopic,
        saveTopicEdit,
        cancelTopicEdit,
    } = useSessionTopics({
        selectedSession,
        selectedSessionDbId,
        sessionSummary,
        originalTopics,
        originalSessionSummary,
        cloneValue,
        showNotification,
    });
    const {
        showTranscript,
        transcriptData,
        loadingTranscript,
        editingTranscript,
        editedTranscriptEntries,
        viewTranscript,
        closeTranscript,
        startEditingTranscript,
        saveTranscriptChanges,
        cancelTranscriptEdit,
    } = useSessionTranscript({
        selectedSessionRef,
        selectedSessionDbId,
        showNotification,
    });

    const applyTranslationToView = async (language, options = {}) => {
        const { notify = true } = options;
        const targetLanguage = (language || '').trim();
        const session = selectedSession.value;
        if (!session || !targetLanguage) {
            return false;
        }

        if (translatedLanguage.value && translatedLanguage.value.toLowerCase() === targetLanguage.toLowerCase()) {
            return true;
        }

        loadingTopics.value = true;
        try {
            const summaryResult = await sessionService.translateSessionSummary(session.id, targetLanguage);
            if (!summaryResult.translated_summary) {
                throw new Error('Translated summary was not returned by the server');
            }

            const translatedSummary = summaryResult.translated_summary;
            sessionSummary.value = translatedSummary;
            setTopicsFromSummary(translatedSummary);
            translatedLanguage.value = targetLanguage;

            if (notify) {
                showNotification('Success', `Content translated to ${targetLanguage}`, 'success');
            }
            return true;
        } catch (error) {
            console.error('Translation failed:', error);

            if (originalSessionSummary.value) {
                sessionSummary.value = cloneValue(originalSessionSummary.value);
            }
            if (originalTopics.value.length > 0) {
                topics.value = cloneValue(originalTopics.value);
            }
            translatedLanguage.value = '';

            if (notify) {
                showNotification('Error', `Translation failed: ${error.message}`, 'error');
            }
            return false;
        } finally {
            loadingTopics.value = false;
        }
    };

    const translateCurrentSummary = async () => {
        const targetLanguage = (selectedLanguage.value || '').trim();
        if (!targetLanguage) {
            showNotification('Warning', 'Enter a target language first.', 'info');
            return;
        }
        await applyTranslationToView(targetLanguage);
    };

    return {
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
    };
}
