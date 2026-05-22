import { ref } from 'vue';
import { sessionService } from '../services/session_service.js';
import { cleanTranscriptText, normalizeSpeaker } from '../utils/text.js';

export function useSessionTranscript({
    selectedSessionRef,
    selectedSessionDbId,
    showNotification,
}) {
    const showTranscript = ref(false);
    const transcriptData = ref([]);
    const loadingTranscript = ref(false);
    const editingTranscript = ref(false);
    const editedTranscriptEntries = ref([]);

    const viewTranscript = async () => {
        if (!selectedSessionRef.value) {
            showNotification('Warning', 'No session selected', 'info');
            return;
        }

        if (showTranscript.value) {
            showTranscript.value = false;
            return;
        }

        loadingTranscript.value = true;
        try {
            const transcript = await sessionService.getSessionTranscript(selectedSessionRef.value);
            const cleanedTranscript = transcript
                .map(entry => ({
                    ...entry,
                    text: cleanTranscriptText(entry.text),
                    speaker: normalizeSpeaker(entry.speaker),
                }))
                .filter(entry => entry.text && entry.text.length > 0);

            transcriptData.value = cleanedTranscript;
            editedTranscriptEntries.value = cleanedTranscript.map(entry => ({ ...entry }));
            showTranscript.value = true;
        } catch (error) {
            console.error('Failed to load transcript:', error);
            showNotification('Error', 'Failed to load transcript data. Please try again.', 'error');
        } finally {
            loadingTranscript.value = false;
        }
    };

    const closeTranscript = () => {
        showTranscript.value = false;
        editingTranscript.value = false;
        transcriptData.value = [];
        editedTranscriptEntries.value = [];
    };

    const startEditingTranscript = () => {
        editingTranscript.value = true;
    };

    const saveTranscriptChanges = async () => {
        if (!selectedSessionDbId.value) {
            showNotification('Warning', 'No session selected', 'info');
            return;
        }

        try {
            await sessionService.updateSessionTranscript(
                selectedSessionDbId.value,
                editedTranscriptEntries.value
            );
            transcriptData.value = [...editedTranscriptEntries.value];
            editingTranscript.value = false;
            showNotification('Success', 'Transcript saved successfully', 'success');
        } catch (error) {
            console.error('Failed to save transcript:', error);
            showNotification('Error', 'Failed to save transcript changes. Please try again.', 'error');
        }
    };

    const cancelTranscriptEdit = () => {
        editedTranscriptEntries.value = transcriptData.value.map(entry => ({ ...entry }));
        editingTranscript.value = false;
    };

    return {
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
    };
}
