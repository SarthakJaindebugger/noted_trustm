import { sessionService } from './session_service.js';
import { authService } from './auth_service.js';
import { config } from '../config.js';
import { resampleAudio } from '../utils/audio.js';

class RecordingService {
    constructor() {
        this.websocket = null;
        this.isRecording = false;
        this.messageHandler = null;
        this.statusHandler = null;
        this.connectionLostHandler = null;
        this.stream = null;
        this.audioContext = null;
        this.analyser = null;
        this.microphoneSource = null;
        this.scriptProcessor = null;
    }

    setHandlers({ onMessage, onStatusChange, onConnectionLost } = {}) {
        this.messageHandler = onMessage || null;
        this.statusHandler = onStatusChange || null;
        this.connectionLostHandler = onConnectionLost || null;
    }

    updateStatus(status) {
        if (this.statusHandler) {
            this.statusHandler(status);
        }
    }

    isAudioSocketOpen() {
        return this.websocket?.readyState === WebSocket.OPEN;
    }

    async connectAudioSocket(sessionId, handlers = {}) {
        this.setHandlers(handlers);
        this.updateStatus('connecting');

        return new Promise((resolve, reject) => {
            try {
                const websocketSessionId = sessionService.getWebSocketSessionId();
                if (!websocketSessionId) {
                    reject(new Error('WebSocket session ID not found in cookies'));
                    return;
                }

                const authToken = authService.getToken();
                if (!authToken) {
                    reject(new Error('Authentication token not found for WebSocket connection'));
                    return;
                }

                const wsUrl = `${config.getWebSocketBaseUrl()}/ws/audio/${websocketSessionId}?access_token=${encodeURIComponent(authToken)}`;
                this.websocket = new WebSocket(wsUrl);
                
                this.websocket.onopen = () => {
                    console.log('WebSocket connection established for session:', sessionId);
                    this.updateStatus('connected');
                    resolve();
                };
                
                this.websocket.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        console.log('Received from backend:', data);
                        if (this.messageHandler) {
                            this.messageHandler(data);
                        }
                    } catch (error) {
                        console.error('Failed to parse WebSocket message:', error);
                    }
                };
                
                this.websocket.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    this.updateStatus('error');
                    this.handleConnectionLoss('WebSocket error');
                    reject(error);
                };
                
                this.websocket.onclose = (event) => {
                    console.log('WebSocket connection closed', event);
                    this.updateStatus('disconnected');
                    
                    if (this.isRecording && event.code !== 1000) {
                        this.handleConnectionLoss('WebSocket disconnected unexpectedly');
                    }
                };
                
            } catch (error) {
                reject(error);
            }
        });
    }

    async sendControlCommand(sessionId, command) {
        return new Promise((resolve, reject) => {
            const authToken = authService.getToken();
            if (!authToken) {
                reject(new Error('Authentication token not found for control WebSocket'));
                return;
            }

            const controlWS = new WebSocket(
                `${config.getWebSocketBaseUrl()}/ws/control/${sessionId}?access_token=${encodeURIComponent(authToken)}`
            );

            controlWS.onopen = () => {
                controlWS.send(JSON.stringify({ command }));
                controlWS.close();
                resolve();
            };

            controlWS.onerror = (error) => {
                console.error(`Failed to send control command "${command}":`, error);
                reject(error);
            };
        });
    }

    disconnectAudioSocket() {
        if (!this.websocket) {
            return;
        }

        this.websocket.close();
        this.websocket = null;
        this.updateStatus('disconnected');
    }

    sendAudioChunk(audioChunk) {
        if (!this.isAudioSocketOpen()) {
            return false;
        }

        this.websocket.send(audioChunk);
        return true;
    }

    async startMicrophoneCapture({ shouldDropAudio = () => false, onChunk } = {}) {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000,
                    channelCount: 1,
                },
            });

            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.microphoneSource = this.audioContext.createMediaStreamSource(this.stream);

            this.analyser.fftSize = 256;
            this.analyser.smoothingTimeConstant = 0.8;
            this.microphoneSource.connect(this.analyser);

            const processingBufferSize = 1024;
            const targetSampleRate = 16000;
            const originalSampleRate = this.audioContext.sampleRate;
            const sendBufferSize = targetSampleRate * 5;
            let audioBuffer = new Float32Array(0);

            console.log(`Audio setup: Original SR: ${originalSampleRate}, Target SR: ${targetSampleRate}`);

            this.scriptProcessor = this.audioContext.createScriptProcessor(processingBufferSize, 1, 1);
            this.scriptProcessor.onaudioprocess = (event) => {
                if (shouldDropAudio()) {
                    audioBuffer = new Float32Array(0);
                    return;
                }

                const inputData = event.inputBuffer.getChannelData(0);
                const resampledData = originalSampleRate !== targetSampleRate
                    ? resampleAudio(inputData, originalSampleRate, targetSampleRate)
                    : inputData;

                const combinedBuffer = new Float32Array(audioBuffer.length + resampledData.length);
                combinedBuffer.set(audioBuffer, 0);
                combinedBuffer.set(resampledData, audioBuffer.length);
                audioBuffer = combinedBuffer;

                while (audioBuffer.length >= sendBufferSize) {
                    const chunk = audioBuffer.slice(0, sendBufferSize);
                    if (onChunk) {
                        onChunk(chunk);
                    }
                    audioBuffer = audioBuffer.slice(sendBufferSize);
                }
            };

            this.microphoneSource.connect(this.scriptProcessor);
            this.scriptProcessor.connect(this.audioContext.destination);

            return {
                analyser: this.analyser,
                audioContext: this.audioContext,
            };
        } catch (error) {
            console.error('Failed to initialize microphone capture:', error);
            await this.stopMicrophoneCapture();
            throw error;
        }
    }

    async stopMicrophoneCapture() {
        if (this.scriptProcessor) {
            this.scriptProcessor.disconnect();
            this.scriptProcessor.onaudioprocess = null;
            this.scriptProcessor = null;
        }

        if (this.microphoneSource) {
            try {
                this.microphoneSource.disconnect();
            } catch (error) {
                console.warn('Microphone source disconnect failed:', error);
            }
            this.microphoneSource = null;
        }

        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }

        if (this.audioContext && this.audioContext.state !== 'closed') {
            await this.audioContext.close();
        }

        this.audioContext = null;
        this.analyser = null;
    }

    handleConnectionLoss(reason) {
        console.log('Connection loss detected:', reason);
        
        // Auto-stop recording
        if (this.isRecording) {
            this.isRecording = false;

            if (this.connectionLostHandler) {
                this.connectionLostHandler({ reason });
            }
            
            console.log('Recording automatically stopped due to connection loss');
        }
    }
}

export const recordingService = new RecordingService();
