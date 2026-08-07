import { ref, computed, onMounted, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { authService } from '../services/auth_service.js';
import { sessionService } from '../services/session_service.js';
import { apiClient } from '../services/api_client.js';

export default {
    name: 'Dashboard',
    setup() {
        const router = useRouter();
        const fileInput = ref(null);
        const isUploading = ref(false);
        const uploadProgress = ref(0);
        const message = ref('');
        const error = ref('');

        // ----- Analyze Audio State -----
        const completedAudioFiles = ref([]);
        const newAudioFiles = ref([]);
        const audioFiles = ref([]);
        const selectedPaths = reactive(new Set()); // Multi-select: audio paths (only from newAudioFiles)
        const processingQueue = ref([]); // Queue of paths to process
        const currentProcessingPath = ref(null); // Currently processing audio
        const processingProgress = ref(null); // { path, percent, status }
        const analysisResults = reactive({}); // { path: result }
        const crmFormStatusCache = reactive({}); // { filename: exists }

        // Computed helpers
        const isAnalyzing = computed(() => processingQueue.value.length > 0 || currentProcessingPath.value !== null);

        const selectAllChecked = computed(() => {
            return newAudioFiles.value.length > 0 && newAudioFiles.value.every(af => selectedPaths.has(af.path));
        });

        const selectAllIndeterminate = computed(() => {
            return selectedPaths.size > 0 && !selectAllChecked.value;
        });

        // Parse date/time from audio file path or use file modification time
        const parseAudioFileInfo = (audioFile) => {
            const name = audioFile.display_name || audioFile.name;
            // Try to extract date from path, fallback to current date
            const date = new Date().toLocaleDateString('de-DE'); // DD.MM.YYYY
            const time = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return { name, date, time };
        };

        const toggleAudioSelection = (audioPath) => {
            if (selectedPaths.has(audioPath)) {
                selectedPaths.delete(audioPath);
            } else {
                selectedPaths.add(audioPath);
            }
        };

        const toggleSelectAll = () => {
            if (selectAllChecked.value) {
                selectedPaths.clear();
            } else {
                newAudioFiles.value.forEach(af => selectedPaths.add(af.path));
            }
        };

        const chooseAudio = () => {
            fileInput.value?.click();
        };

        const logout = async () => {
            authService.logout();
            await router.push({ name: 'login' });
        };

        const uploadAudio = async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;

            isUploading.value = true;
            uploadProgress.value = 0;
            message.value = '';
            error.value = '';

            try {
                const result = await sessionService.uploadUserAudio(file, (progress) => {
                    uploadProgress.value = progress;
                });
                uploadProgress.value = 100;
                message.value = result.message || 'Uploaded successfully.';
                await loadAudioFiles();
            } catch (uploadError) {
                error.value = uploadError.message || 'Unable to upload the audio file.';
            } finally {
                isUploading.value = false;
                event.target.value = '';
            }
        };

        const loadAudioFiles = async () => {
            try {
                const data = await apiClient.get('/audio/analyze-files-categorized');
                completedAudioFiles.value = (data.completed || []).sort((a, b) => a.name.localeCompare(b.name));
                newAudioFiles.value = (data.new || []).sort((a, b) => a.name.localeCompare(b.name));
                audioFiles.value = [...completedAudioFiles.value, ...newAudioFiles.value];
                selectedPaths.clear();
            } catch (loadError) {
                console.error('Failed to load audio files', loadError);
                error.value = loadError.message || 'Failed to load audio files.';
            }
        };

        const checkCrmFormStatus = async (audioFilename) => {
            try {
                const response = await apiClient.get(`/audio/crm-form-status?audio_filename=${encodeURIComponent(audioFilename)}`);
                crmFormStatusCache[audioFilename] = response.crm_form_exists || false;
            } catch (err) {
                console.error('Failed to check CRM form status', err);
                crmFormStatusCache[audioFilename] = false;
            }
        };

        const isCrmFormAvailable = (audioFile) => {
            // CRM is available if: analysis is complete (in results) OR form already exists
            const hasAnalysis = analysisResults[audioFile.path];
            const formExists = crmFormStatusCache[audioFile.name];
            return hasAnalysis || formExists;
        };

        const startBatchAnalysis = async () => {
            if (selectedPaths.size === 0) {
                error.value = 'Please select at least one audio file.';
                return;
            }

            // Sort selected paths alphabetically and queue them
            processingQueue.value = Array.from(selectedPaths).sort();
            selectedPaths.clear();
            error.value = '';
            message.value = '';
            
            // Process queue sequentially
            await processQueueSequentially();
        };

        const processQueueSequentially = async () => {
            while (processingQueue.value.length > 0) {
                const audioPath = processingQueue.value.shift();
                currentProcessingPath.value = audioPath;
                processingProgress.value = { path: audioPath, percent: 0, status: 'Starting analysis...' };

                try {
                    processingProgress.value.status = 'Analyzing audio...';
                    processingProgress.value.percent = 50;

                    const result = await apiClient.post('/audio/analyze', { audio_path: audioPath });
                    analysisResults[audioPath] = result;

                    processingProgress.value.percent = 100;
                    processingProgress.value.status = 'Analysis complete';
                    
                    // Check if CRM form now exists
                    const audioFile = audioFiles.value.find(af => af.path === audioPath);
                    if (audioFile) {
                        await checkCrmFormStatus(audioFile.name);
                    }

                    // Wait briefly before next analysis
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (analyzeError) {
                    console.error('Audio analysis failed for', audioPath, analyzeError);
                    processingProgress.value.status = `Analysis failed: ${analyzeError.message || 'Unknown error'}`;
                    processingProgress.value.percent = 100;
                    
                    // Continue with next file
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }

            currentProcessingPath.value = null;
            processingProgress.value = null;
            message.value = 'Batch analysis complete.';
            await loadAudioFiles();
        };

        const cancelBatchAnalysis = () => {
            processingQueue.value = [];
            currentProcessingPath.value = null;
            processingProgress.value = null;
            message.value = '';
        };

        const openCrmForm = async (audioFile) => {
            // Try in-memory result first, then fall back to fetching from backend
            let result = analysisResults[audioFile.path];

            if (!result) {
                // Already analyzed (page refresh) — fetch the result paths from backend
                try {
                    result = await apiClient.get(`/audio/analyze-result?audio_path=${encodeURIComponent(audioFile.path)}`);
                    if (result) {
                        analysisResults[audioFile.path] = result;
                    }
                } catch (fetchErr) {
                    console.error('Could not fetch existing analysis result', fetchErr);
                }
            }

            if (!result) {
                error.value = 'No analysis result found. Please analyze this file first.';
                return;
            }

            const htmlPath = result.crm_form_html_path || result.result?.crm_form_html_path || '';
            if (!htmlPath) {
                error.value = 'No CRM form HTML is available yet.';
                return;
            }

            // Copy the CRM JSON to submitted_crm_forms when user opens the form
            try {
                await apiClient.post('/audio/crm-form/submit', { audio_filename: audioFile.name });
                // Update CRM form status cache
                crmFormStatusCache[audioFile.name] = true;
            } catch (submitErr) {
                console.warn('Could not copy CRM JSON on open:', submitErr.message);
                // Non-fatal — still open the form
            }

            try {
                const response = await apiClient.request(`/audio/file-content?path=${encodeURIComponent(htmlPath)}`);
                if (!response.ok) {
                    const errText = await response.text();
                    throw new Error(errText || `Failed to open CRM form: ${response.status}`);
                }

                const data = await response.json();
                let htmlContent = data.content || '';

                // Inject auth token and backend URL so the popup can POST back on submit
                const { config } = await import('../config.js');
                const backendUrl = config.getApiBaseUrl().replace('/api/v1', '');
                const authToken = sessionStorage.getItem('auth_token') || '';
                const tokenScript = `<script>window.crmBackendUrl = ${JSON.stringify(backendUrl)};window.crmAuthToken = ${JSON.stringify(authToken)};<\/script>`;

                if (htmlContent.includes('</head>')) {
                    htmlContent = htmlContent.replace('</head>', `${tokenScript}</head>`);
                } else {
                    htmlContent = tokenScript + htmlContent;
                }

                const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
                const blobUrl = URL.createObjectURL(blob);
                const popup = window.open(blobUrl, '_blank', 'noopener,noreferrer');
                if (!popup) {
                    throw new Error('Popup blocked. Please allow popups for this site.');
                }
                setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
                message.value = 'CRM form opened in a new window.';
            } catch (openError) {
                console.error('Failed to open CRM form', openError);
                error.value = openError.message || 'Failed to open CRM form.';
            }
        };

        onMounted(() => {
            loadAudioFiles();
        });

        return {
            fileInput, isUploading, uploadProgress, message, error, chooseAudio, uploadAudio, logout,
            audioFiles, completedAudioFiles, newAudioFiles,
            selectedPaths, isAnalyzing, selectAllChecked, selectAllIndeterminate,
            processingProgress, analysisResults, crmFormStatusCache,
            loadAudioFiles, toggleAudioSelection, toggleSelectAll, startBatchAnalysis, cancelBatchAnalysis,
            isCrmFormAvailable, openCrmForm, parseAudioFileInfo,
        };
    },
    template: `
    <div class="min-h-screen bg-gradient-to-br from-blue-50 via-white to-cyan-50">

      <!-- ── Sticky Header ── -->
      <div class="sticky top-0 z-10 backdrop-blur-md bg-white/70 border-b border-white/30">
        <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 class="text-3xl font-bold text-blue-900">Audio Dashboard</h1>
            <p class="text-gray-500 text-sm">Upload, analyze, and manage your audio recordings</p>
          </div>
          <div class="flex gap-3">
            <button @click="chooseAudio" :disabled="isUploading"
              class="px-5 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 transition text-sm font-medium disabled:opacity-50">
              {{ isUploading ? 'Uploading...' : 'Upload Audio' }}
            </button>
            <button @click="loadAudioFiles"
              class="px-5 py-2 rounded-xl border border-gray-300 text-gray-700 hover:bg-gray-100 transition text-sm font-medium">
              Refresh
            </button>
            <button @click="logout"
              class="px-5 py-2 rounded-xl bg-red-500 text-white hover:bg-red-600 transition text-sm font-medium">
              Logout
            </button>
          </div>
        </div>
      </div>

      <input ref="fileInput" type="file" accept="audio/*" class="sr-only" @change="uploadAudio">

      <!-- ── Status messages ── -->
      <div class="max-w-7xl mx-auto px-6 pt-4">
        <div v-if="isUploading" class="mb-4">
          <div class="w-full h-2 rounded-full bg-gray-200 overflow-hidden">
            <div class="h-full bg-blue-600 rounded-full transition-all duration-300" :style="{ width: uploadProgress + '%' }"></div>
          </div>
          <p class="text-sm text-gray-500 mt-1">Uploading {{ uploadProgress }}%</p>
        </div>
        <div v-if="message" class="mb-4 px-4 py-3 rounded-xl bg-green-50 border border-green-200 text-green-700 text-sm">{{ message }}</div>
        <div v-if="error" class="mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">{{ error }}</div>
      </div>

      <!-- ── Processing progress ── -->
      <div v-if="isAnalyzing" class="max-w-7xl mx-auto px-6 mb-6">
        <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100">
          <div class="flex items-center justify-between mb-3">
            <span class="text-sm font-medium text-gray-700">{{ processingProgress?.status || 'Processing...' }}</span>
            <button @click="cancelBatchAnalysis"
              class="px-3 py-1.5 rounded-lg border border-red-300 text-red-600 hover:bg-red-50 text-xs font-medium transition">
              Cancel
            </button>
          </div>
          <div class="w-full h-2 rounded-full bg-gray-200 overflow-hidden">
            <div class="h-full bg-blue-600 rounded-full animate-pulse" style="width: 60%"></div>
          </div>
        </div>
      </div>

      <!-- ── Side-by-side floating cards ── -->
      <div class="max-w-7xl mx-auto px-6 pb-10 grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">

        <!-- LEFT CARD: Completed Audio Analysis -->
        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <!-- Card header -->
          <div class="px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-green-50 to-emerald-50">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl bg-green-100 flex items-center justify-center">
                <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
              <div>
                <h2 class="text-lg font-bold text-gray-900">Completed Audio Analysis</h2>
                <p class="text-xs text-gray-500">Analyzed recordings with CRM forms ready</p>
              </div>
            </div>
          </div>
          <!-- Card body -->
          <div class="p-0">
            <div v-if="completedAudioFiles.length > 0" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                    <th class="px-4 py-3">S.No.</th>
                    <th class="px-4 py-3">Audio File</th>
                    <th class="px-4 py-3 text-center">CRM Form</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(audioFile, index) in completedAudioFiles" :key="audioFile.path"
                    class="border-b border-gray-50 hover:bg-green-50/50 transition">
                    <td class="px-4 py-3 text-gray-500">{{ index + 1 }}</td>
                    <td class="px-4 py-3 font-medium text-gray-800">{{ parseAudioFileInfo(audioFile).name }}</td>
                    <td class="px-4 py-3 text-center">
                      <button @click="openCrmForm(audioFile)"
                        class="px-3 py-1.5 rounded-lg bg-green-600 text-white text-xs font-medium hover:bg-green-700 transition shadow-sm">
                        Open CRM
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="px-6 py-12 text-center">
              <div class="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
              </div>
              <p class="text-gray-400 text-sm">No completed analyses yet</p>
            </div>
          </div>
        </div>

        <!-- RIGHT CARD: New Audios -->
        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <!-- Card header -->
          <div class="px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-blue-50 to-indigo-50">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-blue-100 flex items-center justify-center">
                  <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
                  </svg>
                </div>
                <div>
                  <h2 class="text-lg font-bold text-gray-900">New Audios</h2>
                  <p class="text-xs text-gray-500">Select and analyze pending recordings</p>
                </div>
              </div>
              <button v-if="!isAnalyzing && newAudioFiles.length > 0"
                @click="startBatchAnalysis"
                :disabled="selectedPaths.size === 0"
                class="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition disabled:opacity-40 disabled:cursor-not-allowed shadow-sm">
                Analyze ({{ selectedPaths.size }})
              </button>
            </div>
          </div>
          <!-- Card body -->
          <div class="p-0">
            <div v-if="!isAnalyzing && newAudioFiles.length > 0" class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
                    <th class="px-4 py-3 w-12">
                      <input type="checkbox" @change="toggleSelectAll"
                        :checked="selectAllChecked" :indeterminate="selectAllIndeterminate"
                        class="w-4 h-4 cursor-pointer accent-blue-600 rounded" />
                    </th>
                    <th class="px-4 py-3">S.No.</th>
                    <th class="px-4 py-3">Audio File</th>
                    <th class="px-4 py-3 text-center">CRM Form</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(audioFile, index) in newAudioFiles" :key="audioFile.path"
                    class="border-b border-gray-50 hover:bg-blue-50/50 transition cursor-pointer"
                    @click="toggleAudioSelection(audioFile.path)">
                    <td class="px-4 py-3">
                      <input type="checkbox"
                        :checked="selectedPaths.has(audioFile.path)"
                        @click.stop="toggleAudioSelection(audioFile.path)"
                        class="w-4 h-4 cursor-pointer accent-blue-600 rounded" />
                    </td>
                    <td class="px-4 py-3 text-gray-500">{{ index + 1 }}</td>
                    <td class="px-4 py-3 font-medium text-gray-800">{{ parseAudioFileInfo(audioFile).name }}</td>
                    <td class="px-4 py-3 text-center">
                      <button @click.stop="openCrmForm(audioFile)"
                        :disabled="!isCrmFormAvailable(audioFile)"
                        class="px-3 py-1.5 rounded-lg border text-xs font-medium transition shadow-sm"
                        :class="isCrmFormAvailable(audioFile)
                          ? 'bg-green-600 text-white border-green-600 hover:bg-green-700'
                          : 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'">
                        Open CRM
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else-if="!isAnalyzing && newAudioFiles.length === 0 && completedAudioFiles.length > 0" class="px-6 py-12 text-center">
              <div class="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
              </div>
              <p class="text-gray-500 text-sm font-medium">All audio files have been analyzed</p>
            </div>
            <div v-else-if="!isAnalyzing" class="px-6 py-12 text-center">
              <div class="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
                <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
                </svg>
              </div>
              <p class="text-gray-400 text-sm">No audio files found. Upload some to get started.</p>
            </div>
          </div>
        </div>

      </div>
    </div>
    `,
};
