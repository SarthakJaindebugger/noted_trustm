import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { recordingService } from '../services/recording_service.js';
import { sessionService } from '../services/session_service.js';

export function useRecordingSessionControls({
    sessionId,
    isResuming,
    handleBackendMessage,
    loadExistingSession,
    startRecordingTimer,
    stopRecordingTimer,
    startWaveformVisualization,
    stopWaveformVisualization,
    setAnalyser,
}) {
    const router = useRouter();
    const isRecording = ref(false);
    const isPaused = ref(false);
    const isProcessingRecording = ref(false);
    const connectionStatus = ref('disconnected');
    const showFinishSessionPopup = ref(false);

    const stopMicrophoneStream = async () => {
        await recordingService.stopMicrophoneCapture();
        setAnalyser(null);
    };

    const stopRecordingUi = async ({ disconnectAudioSocket = false } = {}) => {
        isRecording.value = false;
        recordingService.isRecording = false;
        isPaused.value = false;
        stopRecordingTimer();
        stopWaveformVisualization();

        await stopMicrophoneStream();

        if (disconnectAudioSocket) {
            recordingService.disconnectAudioSocket();
        }
    };

    const initializeMicrophone = async () => {
        try {
            const capture = await recordingService.startMicrophoneCapture({
                shouldDropAudio: () => isPaused.value,
                onChunk: (chunk) => {
                    recordingService.sendAudioChunk(chunk.buffer);
                },
            });

            setAnalyser(capture.analyser);
            return true;
        } catch (error) {
            console.error('Failed to initialize microphone:', error);
            return false;
        }
    };

    const stopRecordingDueToConnectionLoss = async () => {
        try {
            await stopRecordingUi();
            console.log('Session marked as disconnected and can be resumed from the dashboard');
        } catch (error) {
            console.error('Error stopping recording due to connection loss:', error);
        }
    };

    const startRecording = async () => {
        try {
            await recordingService.connectAudioSocket(sessionId.value, {
                onMessage: handleBackendMessage,
                onStatusChange: (status) => {
                    connectionStatus.value = status;
                },
                onConnectionLost: () => {
                    if (isRecording.value) {
                        void stopRecordingDueToConnectionLoss();
                    }
                },
            });

            const microphoneReady = await initializeMicrophone();
            if (!microphoneReady) {
                recordingService.disconnectAudioSocket();
                return;
            }

            isRecording.value = true;
            recordingService.isRecording = true;
            startRecordingTimer();
            startWaveformVisualization();
        } catch (error) {
            console.error('Failed to start recording:', error);
        }
    };

    const toggleRecording = async () => {
        if (!isRecording.value) {
            return;
        }

        try {
            if (isPaused.value) {
                isPaused.value = false;
                startRecordingTimer();

                if (recordingService.isAudioSocketOpen()) {
                    await recordingService.sendControlCommand(sessionId.value, 'resume');
                }
                return;
            }

            isPaused.value = true;
            stopRecordingTimer();

            if (recordingService.isAudioSocketOpen()) {
                await recordingService.sendControlCommand(sessionId.value, 'pause');
            }
        } catch (error) {
            console.error('Failed to toggle recording:', error);
        }
    };

    const closeFinishSessionPopup = () => {
        showFinishSessionPopup.value = false;
    };

    const showFinishSessionDialog = async () => {
        if (isRecording.value || isPaused.value) {
            await stopRecordingUi();
        }

        showFinishSessionPopup.value = true;
    };

    const navigateToDashboard = async () => {
        await router.push({ name: 'dashboard' });
    };

    const deleteSessionFromPopup = async () => {
        try {
            await stopRecordingUi({ disconnectAudioSocket: true });
            await sessionService.deleteSession(sessionId.value);
        } catch (error) {
            console.error('Failed to delete session:', error);
        } finally {
            closeFinishSessionPopup();
            await navigateToDashboard();
        }
    };

    const openSessionDetailsAfterNavigation = async () => {
        await router.push({
            name: 'session-detail',
            params: { sessionId: sessionId.value },
        });
    };

    const actuallyFinishSession = async () => {
        isProcessingRecording.value = true;

        try {
            await stopRecordingUi();

            if (recordingService.isAudioSocketOpen()) {
                await recordingService.sendControlCommand(sessionId.value, 'stop');
                recordingService.disconnectAudioSocket();
            }

            await sessionService.endSession(sessionId.value);
        } catch (error) {
            console.error('Failed to finish session:', error);
        } finally {
            isProcessingRecording.value = false;
        }
    };

    const saveAndOpenSessionDetails = async () => {
        closeFinishSessionPopup();
        await actuallyFinishSession();
        await openSessionDetailsAfterNavigation();
    };

    const startAnotherSession = async () => {
        if (isRecording.value || isPaused.value) {
            await actuallyFinishSession();
        }

        await router.push({ name: 'new-session' });
    };

    const ensureResumeSessionId = async () => {
        if (!isResuming.value || sessionService.getWebSocketSessionId()) {
            return;
        }

        try {
            const session = await sessionService.getSession(sessionId.value);
            if (session.websocket_session_id) {
                sessionService.setWebSocketSessionId(session.websocket_session_id);
            }
        } catch (error) {
            console.error('Failed to fetch session for resume:', error);
        }
    };

    const initializeRecordingSession = async () => {
        await ensureResumeSessionId();
        await loadExistingSession();
        await startRecording();
    };

    const cleanupRecordingSession = () => {
        recordingService.disconnectAudioSocket();
        recordingService.isRecording = false;
        void recordingService.stopMicrophoneCapture();
        setAnalyser(null);
    };

    return {
        isRecording,
        isPaused,
        isProcessingRecording,
        connectionStatus,
        showFinishSessionPopup,
        toggleRecording,
        showFinishSessionDialog,
        closeFinishSessionPopup,
        deleteSessionFromPopup,
        saveSessionFromPopup: saveAndOpenSessionDetails,
        saveAndEditSummary: saveAndOpenSessionDetails,
        actuallyFinishSession,
        startAnotherSession,
        initializeRecordingSession,
        cleanupRecordingSession,
    };
}
