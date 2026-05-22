import { ref, computed, nextTick } from 'vue';
import { sessionService } from '../services/session_service.js';
import { cleanTranscriptText, normalizeSpeaker } from '../utils/text.js';

const LIVE_TOPIC_KEYWORDS = [
    { topic: 'Employment', keywords: ['work', 'job', 'employment'] },
    { topic: 'Language Learning', keywords: ['language', 'finnish', 'swedish'] },
    { topic: 'CV Support', keywords: ['cv', 'resume'] },
    { topic: 'Education', keywords: ['education', 'course', 'study'] },
];

const createDefaultSummaryData = () => ({
    outputFor: [],
    overview: 'Waiting for conversation to start...',
    actionItems: [],
    relatedServices: [],
});

export function useLiveRecordingSession({ sessionId, transcriptContainer }) {
    const recordingTime = ref(0);
    const conversationEntries = ref([]);
    const currentLanguage = ref('unknown');
    const languageConfidence = ref(0);
    const languageSwitched = ref(false);
    const processingTime = ref(0);
    const summaryData = ref(createDefaultSummaryData());

    const formatTime = computed(() => {
        const minutes = Math.floor(recordingTime.value / 60);
        const seconds = recordingTime.value % 60;
        return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    });

    let recordingInterval = null;
    let entryIdCounter = 0;
    const entrySettleTimeouts = new Map();

    const nextEntryId = () => `live-entry-${Date.now()}-${entryIdCounter++}`;

    const mergeUniqueStrings = (currentItems = [], nextItems = []) => (
        [...new Set([...currentItems, ...nextItems].filter(Boolean))]
    );

    const scheduleEntrySettle = (entry) => {
        entry.isNew = true;

        const existingTimeout = entrySettleTimeouts.get(entry.id);
        if (existingTimeout) {
            clearTimeout(existingTimeout);
        }

        const timeoutId = window.setTimeout(() => {
            entry.isNew = false;
            entrySettleTimeouts.delete(entry.id);
        }, 1000);

        entrySettleTimeouts.set(entry.id, timeoutId);
    };

    const scrollTranscriptToBottom = async () => {
        await nextTick();
        if (transcriptContainer.value) {
            transcriptContainer.value.scrollTop = transcriptContainer.value.scrollHeight;
        }
    };

    const addDetectedTopics = (topics = []) => {
        if (topics.length === 0) {
            return;
        }

        summaryData.value.outputFor = mergeUniqueStrings(summaryData.value.outputFor, topics);
    };

    const detectTopicsFromText = (text = '') => {
        const normalizedText = text.toLowerCase();
        const detectedTopics = LIVE_TOPIC_KEYWORDS
            .filter(({ keywords }) => keywords.some(keyword => normalizedText.includes(keyword)))
            .map(({ topic }) => topic);

        addDetectedTopics(detectedTopics);
    };

    const rebuildTopicsFromConversation = () => {
        const detectedTopics = conversationEntries.value.flatMap(entry => {
            const normalizedText = entry.content.toLowerCase();
            return LIVE_TOPIC_KEYWORDS
                .filter(({ keywords }) => keywords.some(keyword => normalizedText.includes(keyword)))
                .map(({ topic }) => topic);
        });

        addDetectedTopics(detectedTopics);
    };

    const normalizeActionItems = (items = []) => {
        if (!Array.isArray(items)) {
            return [];
        }

        return items
            .map(item => {
                if (!item) {
                    return null;
                }

                if (typeof item === 'string') {
                    return item;
                }

                if (!item.task) {
                    return JSON.stringify(item);
                }

                const parts = [item.task];
                if (item.responsible_party) {
                    parts.push(`Responsible: ${item.responsible_party}`);
                }
                if (item.timeline) {
                    parts.push(`Timeline: ${item.timeline}`);
                }
                return parts.join(' - ');
            })
            .filter(Boolean);
    };

    const normalizeRelatedServices = (themes = []) => {
        if (!Array.isArray(themes)) {
            return [];
        }

        return themes.map(theme => {
            if (typeof theme === 'string') {
                return { name: theme, url: '#' };
            }

            if (theme && typeof theme === 'object') {
                return {
                    name: theme.name || theme.topic || 'Related Item',
                    url: theme.url || '#',
                };
            }

            return { name: String(theme), url: '#' };
        });
    };

    const updateSummary = (summary) => {
        if (!summary) {
            return;
        }

        if (typeof summary === 'string') {
            summaryData.value.overview = summary;
            return;
        }

        if (summary.current_summary) {
            summaryData.value.overview = summary.current_summary;

            const liveActionItems = normalizeActionItems(summary.potential_action_items || []);
            if (liveActionItems.length > 0) {
                summaryData.value.actionItems = liveActionItems;
            }

            addDetectedTopics(Array.isArray(summary.topics_so_far) ? summary.topics_so_far : []);
            summaryData.value.relatedServices = normalizeRelatedServices(summary.emerging_themes || []);
            return;
        }

        if (summary.summary) {
            summaryData.value.overview = summary.summary;
        }

        if (Array.isArray(summary.action_items)) {
            summaryData.value.actionItems = normalizeActionItems(summary.action_items);
        }

        if (Array.isArray(summary.key_decisions)) {
            const keyDecisionItems = summary.key_decisions.map(decision => `Key Decision: ${decision}`);
            summaryData.value.actionItems = mergeUniqueStrings(
                summaryData.value.actionItems,
                keyDecisionItems
            );
        }

        if (Array.isArray(summary.topics)) {
            const topicNames = summary.topics.map(topic => (
                typeof topic === 'string' ? topic : topic.topic || 'Unknown Topic'
            ));
            addDetectedTopics(topicNames);
            summaryData.value.relatedServices = normalizeRelatedServices(topicNames);
        }
    };

    const appendConversationEntry = (entry) => {
        const cleanedText = cleanTranscriptText(entry.text);
        if (!cleanedText) {
            return false;
        }

        const normalizedSpeaker = normalizeSpeaker(entry.speaker);
        const lastEntry = conversationEntries.value[conversationEntries.value.length - 1];
        const confidence = Math.round((entry.confidence || 0) * 100) / 100;
        const speakerConfidence = Math.round((entry.speaker_confidence || 0) * 100) / 100;

        if (lastEntry && lastEntry.speaker === normalizedSpeaker) {
            const previousLength = lastEntry.content.length;
            lastEntry.content = `${lastEntry.content} ${cleanedText}`;
            lastEntry.timestamp = new Date().toLocaleTimeString();

            const combinedLength = previousLength + cleanedText.length;
            if (combinedLength > 0) {
                lastEntry.confidence = Math.round(
                    (((lastEntry.confidence || 0) * previousLength) + (confidence * cleanedText.length)) / combinedLength * 100
                ) / 100;
                lastEntry.speaker_confidence = Math.round(
                    (((lastEntry.speaker_confidence || 0) * previousLength) + (speakerConfidence * cleanedText.length)) / combinedLength * 100
                ) / 100;
            }

            scheduleEntrySettle(lastEntry);
            detectTopicsFromText(cleanedText);
            return true;
        }

        const newEntry = {
            id: nextEntryId(),
            speaker: normalizedSpeaker,
            content: cleanedText,
            timestamp: new Date().toLocaleTimeString(),
            confidence,
            speaker_confidence: speakerConfidence,
            language: currentLanguage.value,
            isNew: true,
        };

        conversationEntries.value.push(newEntry);
        scheduleEntrySettle(newEntry);
        detectTopicsFromText(cleanedText);
        return true;
    };

    const handleTranscriptUpdate = async (result) => {
        currentLanguage.value = result.language || 'unknown';
        languageConfidence.value = result.language_confidence || 0;
        languageSwitched.value = result.language_switched || false;
        processingTime.value = result.processing_time || 0;

        if (!Array.isArray(result.conversation_entries) || result.conversation_entries.length === 0) {
            if (result.summary) {
                updateSummary(result.summary);
            }
            return;
        }

        let didAddEntries = false;
        for (const entry of result.conversation_entries) {
            didAddEntries = appendConversationEntry(entry) || didAddEntries;
        }

        if (didAddEntries) {
            await scrollTranscriptToBottom();
        }

        if (result.summary) {
            updateSummary(result.summary);
        }
    };

    const handleBackendMessage = async (data) => {
        if (data.type === 'transcript_update') {
            await handleTranscriptUpdate(data.data);
            return;
        }

        if (data.type === 'error') {
            console.error('Backend error:', data.message);
        }
    };

    const mapTranscriptEntry = (entry) => ({
        id: entry.id || nextEntryId(),
        speaker: normalizeSpeaker(entry.speaker),
        content: cleanTranscriptText(entry.text),
        timestamp: new Date(entry.timestamp).toLocaleTimeString(),
        confidence: entry.confidence,
        speaker_confidence: entry.speaker_confidence,
        language: entry.language || 'unknown',
        isNew: false,
    });

    const loadExistingSession = async () => {
        try {
            const transcript = await sessionService.getSessionTranscript(sessionId.value);
            if (transcript.length === 0) {
                return;
            }

            conversationEntries.value = transcript
                .map(mapTranscriptEntry)
                .filter(entry => entry.content);

            rebuildTopicsFromConversation();
        } catch (error) {
            console.error('Failed to load existing session:', error);
        }
    };

    const startRecordingTimer = () => {
        if (recordingInterval) {
            return;
        }

        recordingInterval = window.setInterval(() => {
            recordingTime.value += 1;
        }, 1000);
    };

    const stopRecordingTimer = () => {
        if (!recordingInterval) {
            return;
        }

        clearInterval(recordingInterval);
        recordingInterval = null;
    };

    const cleanupLiveSession = () => {
        stopRecordingTimer();
        entrySettleTimeouts.forEach(timeoutId => clearTimeout(timeoutId));
        entrySettleTimeouts.clear();
    };

    return {
        recordingTime,
        formatTime,
        conversationEntries,
        currentLanguage,
        languageConfidence,
        languageSwitched,
        processingTime,
        summaryData,
        handleBackendMessage,
        loadExistingSession,
        startRecordingTimer,
        stopRecordingTimer,
        cleanupLiveSession,
    };
}
